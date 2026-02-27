import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import time
import ssl

# --- 核心修復：解決 SSL 憑證驗證失敗問題 ---
ssl._create_default_https_context = ssl._create_unverified_context

# 頁面基礎設定
st.set_page_config(page_title="2026 全台股趨勢終極掃描器", layout="wide")

@st.cache_data(ttl=86400)
def get_full_taiwan_stock_list():
    """從證交所與櫃買中心獲取清單，並加入強健的過濾機制"""
    stocks = []
    try:
        # 上市與上櫃清單網址 (使用證交所官方 JSP 清單)
        urls = [
            ("https://isin.twse.com.tw", ".TW"),
            ("https://isin.twse.com.tw", ".TWO")
        ]
        
        for url, suffix in urls:
            # 讀取 HTML 表格
            df_list = pd.read_html(url)
            df = df_list[0]
            
            # 設定欄位並跳過標題行
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            for item in df['有價證券代號及名稱']:
                if pd.isna(item): continue
                # 處理「代號 名称」之間的空格 (全形/半形)
                parts = item.replace('　', ' ').split(' ')
                if len(parts) >= 2:
                    code = parts[0]
                    name = parts[1]
                    # 篩選 4 碼普通股 (排除權證、認購與 ETF)
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

def analyze_chunk(df_chunk, selected_stocks_chunk, order):
    """分析掃描邏輯：底底高 + 20MA"""
    results = []
    if df_chunk is None or df_chunk.empty:
        return results

    for s in selected_stocks_chunk:
        symbol = s['symbol']
        try:
            # 檢查是否存在該股資料且 Close 欄位非空
            if symbol not in df_chunk['Close'].columns:
                continue
                
            series = df_chunk['Close'][symbol].dropna()
            if len(series) < 40: continue
            
            prices = series.values
            # 抓取局部極小值點 (低點)
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            
            if len(low_idx) < 2: continue
            
            last_low = float(prices[low_idx[-1]])
            prev_low = float(prices[low_idx[-2]])
            curr_price = float(prices[-1])
            ma20 = float(series.rolling(20).mean().iloc[-1])
            
            # 核心策略：最新低點大於前一低點 (底底高) 且 現價高於 20MA
            if last_low > prev_low and curr_price > ma20:
                results.append({
                    "股票名稱": s['label'],
                    "代號": s['code'],
                    "現價": round(curr_price, 2),
                    "建議買進": round(last_low * 1.005, 2),
                    "建議賣出": round(curr_price * 1.10, 2),
                    "支撐價位": round(last_low, 2),
                    "趨勢幅度": f"{round((curr_price/last_low-1)*100, 1)}%"
                })
        except:
            continue
    return results

# --- UI 介面 ---
st.title("🛡️ TW 2026 全台股趨勢終極掃描系統")
st.markdown("本模式將遍歷**全台上市櫃 1,800+ 檔個股**，自動篩選**底底高**且**站上 20MA** 的標的。")

with st.sidebar:
    st.header("掃描設定")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 8, help="數值越小標的越多，數值越大越嚴格")
    st.info("💡 全台股掃描約需 3-5 分鐘，請保持網頁開啟。")
    start_btn = st.button("🔥 啟動全台股深度掃描")

if start_btn:
    all_stocks = get_full_taiwan_stock_list()
    
    if not all_stocks:
        st.error("無法載入股票清單，請檢查網路連線或稍後再試。")
    else:
        total_count = len(all_stocks)
        chunk_size = 40  # 降低批次數量以避免觸發 API 限制
        all_results = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.spinner("系統正在深度分析全台股..."):
            for i in range(0, total_count, chunk_size):
                chunk = all_stocks[i : i + chunk_size]
                symbols = [s['symbol'] for s in chunk]
                
                status_text.text(f"進度: {i} / {total_count} (正在掃描第 {i//chunk_size + 1} 區段)")
                
                try:
                    # 抓取最近 6 個月的日線資料
                    df_batch = yf.download(symbols, period="6mo", progress=False, group_by='column')
                    chunk_results = analyze_chunk(df_batch, chunk, sens)
                    all_results.extend(chunk_results)
                except Exception:
                    pass
                
                # 更新進度
                progress_bar.progress(min((i + chunk_size) / total_count, 1.0))
                time.sleep(0.3) # 增加穩定性

        status_text.text("✅ 全台股掃描完成！")

        if all_results:
            final_df = pd.DataFrame(all_results)
            final_df = final_df.sort_values(by="代號")
            
            st.success(f"🎉 掃描完畢！找到 {len(final_df)} 檔符合「底底高 + 20MA」之標的。")
            st.dataframe(final_df, use_container_width=True)
        else:
            st.warning("☹️ 當前靈敏度下未發現符合標的，建議調整靈敏度後重試。")
