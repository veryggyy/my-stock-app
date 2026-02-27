import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import time
import ssl

# --- 核心修復：強制忽略 SSL 驗證，解決 CERTIFICATE_VERIFY_FAILED 錯誤 ---
ssl._create_default_https_context = ssl._create_unverified_context

# 頁面基礎設定
st.set_page_config(page_title="2026 全台股趨勢終極掃描器", layout="wide")

@st.cache_data(ttl=86400)
def get_full_taiwan_stock_list():
    """直接從證交所官方 HTML 抓取最新清單，並校正格式"""
    stocks = []
    try:
        # 上市 (SII) 與 上櫃 (OTC) 官方 JSP 清單網址
        urls = [
            ("https://isin.twse.com.tw", ".TW"),
            ("https://isin.twse.com.tw", ".TWO")
        ]
        
        for url, suffix in urls:
            # 讀取 HTML 表格 (需安裝 lxml 庫)
            df_list = pd.read_html(url)
            df = df_list[0]
            
            # 整理格式：設定欄位並跳過標題行
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            for item in df['有價證券代號及名稱']:
                if pd.isna(item): continue
                # 處理「2330　台積電」這種帶有全型空格的格式
                parts = item.replace('　', ' ').split(' ')
                if len(parts) >= 2:
                    code = parts[0]
                    name = parts[1]
                    # 篩選 4 碼純數字普通股，剔除權證與 ETF
                    if len(code) == 4 and code.isdigit():
                        stocks.append({
                            "label": name, 
                            "code": code, 
                            "symbol": f"{code}{suffix}"
                        })
        return stocks
    except Exception as e:
        st.error(f"清單獲取失敗，錯誤回報: {e}")
        return []

def analyze_chunk(df_batch, selected_stocks_chunk, order):
    """核心趨勢邏輯：篩選底底高且站上 20MA 的標的"""
    results = []
    if df_batch is None or df_batch.empty:
        return results

    for s in selected_stocks_chunk:
        symbol = s['symbol']
        try:
            # 檢查 yfinance 抓回的資料中是否有該股 Close 欄位
            if symbol not in df_batch['Close'].columns:
                continue
                
            series = df_batch['Close'][symbol].dropna()
            if len(series) < 40: continue
            
            prices = series.values
            # 尋找波段低點 (Local Minima)
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            
            if len(low_idx) < 2: continue
            
            last_low = float(prices[low_idx[-1]])
            prev_low = float(prices[low_idx[-2]])
            curr_price = float(prices[-1])
            ma20 = float(series.rolling(20).mean().iloc[-1])
            
            # 判斷條件：最新低點 > 前一低點 (底底高) 且 現價 > 20MA
            if last_low > prev_low and curr_price > ma20:
                results.append({
                    "股票名稱": s['label'],
                    "代號": s['code'],
                    "現價": round(curr_price, 2),
                    "支撐價位": round(last_low, 2),
                    "建議買點": round(last_low * 1.01, 2),
                    "趨勢偏離": f"{round((curr_price/last_low-1)*100, 1)}%"
                })
        except:
            continue
    return results

# --- UI 介面 ---
st.title("🛡️ TW 2026 全台股趨勢終極掃描系統")
st.markdown("自動遍歷全台上市櫃約 1,800+ 檔個股，篩選**底底高**且**站上 20MA** 的標的。")

with st.sidebar:
    st.header("掃描設定")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 8, help="建議 5-10 以獲得較多標的")
    st.info("💡 全台股掃描約需 3-5 分鐘，請保持網頁開啟。")
    start_btn = st.button("🔥 啟動全台股深度掃描")

if start_btn:
    all_stocks = get_full_taiwan_stock_list()
    
    if not all_stocks:
        st.error("無法載入股票清單，請檢查網路連線或檢查 SSL 設定。")
    else:
        total_count = len(all_stocks)
        chunk_size = 40  # 分組下載，避免 API 過載封鎖
        all_results = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.spinner("系統深度掃描進行中..."):
            for i in range(0, total_count, chunk_size):
                chunk = all_stocks[i : i + chunk_size]
                symbols = [s['symbol'] for s in chunk]
                
                status_text.text(f"掃描進度: {i} / {total_count} (正在分析第 {i//chunk_size + 1} 梯次)")
                
                try:
                    # 抓取半年日線資料
                    df_batch = yf.download(symbols, period="6mo", progress=False, group_by='column')
                    chunk_results = analyze_chunk(df_batch, chunk, sens)
                    all_results.extend(chunk_results)
                except Exception:
                    pass 
                
                progress_bar.progress(min((i + chunk_size) / total_count, 1.0))
                time.sleep(0.3) # 防禦性延遲

        status_text.text("✅ 全台股掃描完成！")

        if all_results:
            final_df = pd.DataFrame(all_results)
            final_df = final_df.sort_values(by="現價", ascending=False)
            
            st.success(f"🎉 找到 {len(final_df)} 檔符合底底高標的。")
            st.dataframe(final_df, use_container_width=True)
        else:
            st.warning("☹️ 未發現符合標的，請嘗試調低靈敏度。")
