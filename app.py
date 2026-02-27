import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import time

# 頁面基礎設定
st.set_page_config(page_title="2026 全台股趨勢終極掃描器", layout="wide")

@st.cache_data(ttl=86400)
def get_full_taiwan_stock_list():
    """從證交所與櫃買中心獲取最新完整股票清單"""
    stocks = []
    try:
        # 1. 抓取上市股票清單 (SII)
        url_sii = "https://isin.twse.com.tw"
        # 2. 抓取上櫃股票清單 (OTC)
        url_otc = "https://isin.twse.com.tw"
        
        for url, market_type in [(url_sii, ".TW"), (url_otc, ".TWO")]:
            # 讀取 HTML 表格
            df_list = pd.read_html(url)
            df = df_list[0]
            
            # 整理格式
            df.columns = df.iloc[0] # 設定第一行為欄位名
            df = df.iloc[2:] # 跳過標題行
            
            for item in df['有價證券代號及名稱']:
                if pd.isna(item): continue
                # 原始資料格式為 "2330　台積電" (中間有全型空格)
                parts = item.replace('　', ' ').split(' ')
                if len(parts) >= 2:
                    code = parts[0]
                    name = parts[1]
                    # 篩選 4 碼普通股
                    if len(code) == 4:
                        stocks.append({
                            "label": name, 
                            "code": code, 
                            "symbol": f"{code}{market_type}"
                        })
        return stocks
    except Exception as e:
        st.error(f"清單獲取失敗，錯誤回報: {e}")
        return []

def analyze_chunk(df_chunk, selected_stocks_chunk, order):
    """分析一組批次資料"""
    results = []
    if df_chunk.empty:
        return results

    for s in selected_stocks_chunk:
        symbol = s['symbol']
        try:
            # 處理多重索引 (Multi-index) 的 yfinance 資料
            if symbol not in df_chunk['Close'].columns:
                continue
                
            series = df_chunk['Close'][symbol].dropna()
            if len(series) < 40: continue
            
            prices = series.values
            # 尋找局部極小值
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            
            if len(low_idx) < 2: continue
            
            last_low = float(prices[low_idx[-1]])
            prev_low = float(prices[low_idx[-2]])
            curr_price = float(prices[-1])
            ma20 = float(series.rolling(20).mean().iloc[-1])
            
            # 趨勢邏輯：底底高 (Higher Low) + 站上 20MA
            if last_low > prev_low and curr_price > ma20:
                results.append({
                    "股票名稱": s['label'],
                    "代號": s['code'],
                    "現價": round(curr_price, 2),
                    "建議買進": round(last_low * 1.01, 2),
                    "建議賣出": round(curr_price * 1.10, 2),
                    "支撐價位": round(last_low, 2),
                    "幅度": f"{round((curr_price/last_low-1)*100, 1)}%"
                })
        except:
            continue
    return results

# --- UI 介面 ---
st.title("🛡️ TW 2026 全台股趨勢終極掃描系統")
st.markdown("本模式將遍歷**全台上市櫃約 1,800+ 檔個股**，自動篩選底底高且站上 20MA 的標的。")

with st.sidebar:
    st.header("掃描設定")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 8, help="建議設為 5-10 以獲得較多標的")
    st.info("💡 全台股掃描約需 2-5 分鐘，請保持網頁開啟。")
    start_btn = st.button("🔥 啟動全台股深度掃描")

if start_btn:
    all_stocks = get_full_taiwan_stock_list()
    
    if not all_stocks:
        st.error("無法載入股票清單，請檢查網路連線。")
    else:
        total_count = len(all_stocks)
        chunk_size = 50 # 縮小批次以提高穩定性
        all_results = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.spinner("深度掃描進行中..."):
            for i in range(0, total_count, chunk_size):
                chunk = all_stocks[i : i + chunk_size]
                symbols = [s['symbol'] for s in chunk]
                
                status_text.text(f"正在掃描: {i} ~ {min(i+chunk_size, total_count)} / 總計 {total_count} 檔")
                
                try:
                    # 下載半年資料
                    df_batch = yf.download(symbols, period="6mo", progress=False, group_by='column')
                    chunk_results = analyze_chunk(df_batch, chunk, sens)
                    all_results.extend(chunk_results)
                except Exception as e:
                    pass # 略過異常區段
                
                progress_bar.progress(min((i + chunk_size) / total_count, 1.0))
                time.sleep(0.2) # 短暫休眠避免 API 請求限制

        status_text.text("✅ 全台股深度掃描完成！")

        if all_results:
            final_df = pd.DataFrame(all_results)
            final_df = final_df.sort_values(by="現價", ascending=False)
            
            st.success(f"🎉 掃描完畢！在全台股中找到 {len(final_df)} 檔符合條件標的。")
            
            st.dataframe(
                final_df, 
                use_container_width=True,
                column_config={
                    "現價": st.column_config.NumberColumn(format="%.2f"),
                    "建議買進": st.column_config.NumberColumn(format="%.2f"),
                    "建議賣出": st.column_config.NumberColumn(format="%.2f"),
                    "支撐價位": st.column_config.NumberColumn(format="%.2f")
                }
            )
        else:
            st.warning("☹️ 掃描全台股後未發現符合條件標的，建議調低「趨勢靈敏度」。")
