import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import time
import os

# 頁面基礎設定
st.set_page_config(page_title="2026 全台股趨勢終極掃描系統", layout="wide")

@st.cache_data(ttl=86400)
def get_full_taiwan_stock_list():
    """
    最高穩定度獲取邏輯：優先讀取 GitHub 上的 CSV 檔案。
    """
    cache_file = "taiwan_stock_list.csv"
    
    # 1. 優先從同目錄下的 CSV 檔案讀取 (解決所有 SSL/連線報錯)
    if os.path.exists(cache_file):
        try:
            df = pd.read_csv(cache_file, dtype={'code': str})
            return df.to_dict('records')
        except Exception as e:
            st.error(f"讀取 CSV 失敗: {e}")

    # 2. 如果沒檔案（例如第一次建立），提供核心權值股保底
    return [
        {"label": "台積電", "code": "2330", "symbol": "2330.TW"},
        {"label": "鴻海", "code": "2317", "symbol": "2317.TW"},
        {"label": "聯發科", "code": "2454", "symbol": "2454.TW"},
        {"label": "廣達", "code": "2382", "symbol": "2382.TW"},
        {"label": "長榮", "code": "2603", "symbol": "2603.TW"},
        {"label": "緯創", "code": "3231", "symbol": "3231.TW"}
    ]

def analyze_chunk(df_batch, selected_stocks_chunk, order):
    """分析核心邏輯：篩選底底高且站上 20MA 的標的"""
    results = []
    if df_batch is None or df_batch.empty:
        return results

    for s in selected_stocks_chunk:
        symbol = s['symbol']
        try:
            # 處理 yfinance 多重索引資料結構
            if symbol not in df_batch:
                continue
            
            # 取得收盤價序列
            series = df_batch[symbol]['Close'].dropna()
            if len(series) < 40: continue
            
            prices = series.values
            # 尋找波段低點 (局部極小值)
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            
            if len(low_idx) < 2: continue
            
            last_low = float(prices[low_idx[-1]])
            prev_low = float(prices[low_idx[-2]])
            curr_price = float(prices[-1])
            ma20 = float(series.rolling(20).mean().iloc[-1])
            
            # 策略：最新低點 > 前一低點 (底底高) 且 現價高於 20MA
            if last_low > prev_low and curr_price > ma20:
                results.append({
                    "股票名稱": s['label'],
                    "代號": s['code'],
                    "現價": round(curr_price, 2),
                    "支撐價位": round(last_low, 2),
                    "趨勢偏離": f"{round((curr_price/last_low-1)*100, 1)}%"
                })
        except:
            continue
    return results

# --- UI 介面 ---
st.title("🛡️ TW 2026 全台股趨勢終極掃描系統")
st.markdown("系統目前使用 **CSV 靜態清單** 模式，確保連線 100% 穩定。")

# 預先載入股票清單
all_stocks = get_full_taiwan_stock_list()

with st.sidebar:
    st.header("掃描設定")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 8, help="建議設為 8-10")
    st.info(f"📊 目前清單內含 {len(all_stocks)} 檔標的。")
    start_btn = st.button("🔥 啟動全台股深度掃描")

if start_btn:
    total_count = len(all_stocks)
    chunk_size = 40 # 分組下載，避免 API 頻繁連線被鎖
    all_results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with st.spinner("正在進行大數據分析..."):
        for i in range(0, total_count, chunk_size):
            chunk = all_stocks[i : i + chunk_size]
            symbols = [s['symbol'] for s in chunk]
            
            status_text.text(f"掃描進度: {i} / {total_count}")
            
            try:
                # 下載近 6 個月數據，使用 group_by='ticker' 提高穩定度
                df_batch = yf.download(symbols, period="6mo", progress=False, group_by='ticker', threads=True)
                if not df_batch.empty:
                    chunk_results = analyze_chunk(df_batch, chunk, sens)
                    all_results.extend(chunk_results)
            except Exception as e:
                pass 
            
            # 更新進度條
            progress_bar.progress(min((i + chunk_size) / total_count, 1.0))
            time.sleep(0.5) # 降低對 Yahoo API 的請求頻率

    status_text.text("✅ 全台股深度掃描完成！")

    if all_results:
        final_df = pd.DataFrame(all_results)
        final_df = final_df.sort_values(by="趨勢偏離")
        st.success(f"🎉 在清單中找到 {len(final_df)} 檔符合條件標的。")
        st.dataframe(final_df, use_container_width=True)
    else:
        st.warning("☹️ 目前靈敏度下未發現符合標的，請嘗試調低靈敏度。")
