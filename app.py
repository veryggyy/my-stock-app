import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import time
import os

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="2026 台股趨勢終極掃描系統", layout="wide")

@st.cache_data(ttl=86400)
def get_full_taiwan_stock_list():
    """優先讀取 GitHub/本地 CSV 檔案，失敗則提供核心權值股"""
    cache_file = "taiwan_stock_list.csv"
    if os.path.exists(cache_file):
        try:
            df = pd.read_csv(cache_file, dtype={'code': str})
            return df.to_dict('records')
        except Exception as e:
            st.error(f"讀取 CSV 失敗: {e}")

    return [
        {"label": "台積電", "code": "2330", "symbol": "2330.TW"},
        {"label": "鴻海", "code": "2317", "symbol": "2317.TW"},
        {"label": "聯發科", "code": "2454", "symbol": "2454.TW"},
        {"label": "廣達", "code": "2382", "symbol": "2382.TW"},
        {"label": "長榮", "code": "2603", "symbol": "2603.TW"},
        {"label": "緯創", "code": "3231", "symbol": "3231.TW"}
    ]

# --- 2. 核心分析邏輯 ---
def analyze_chunk(df_batch, selected_stocks_chunk, order):
    results = []
    if df_batch is None or df_batch.empty:
        return results

    for s in selected_stocks_chunk:
        symbol = s['symbol']
        try:
            if symbol not in df_batch: continue
            
            # 取得數據 (Close & Volume)
            data = df_batch[symbol].dropna()
            if len(data) < 40: continue
            
            close_series = data['Close']
            vol_series = data['Volume']
            prices = close_series.values
            
            # A. RSI 計算 (14日)
            delta = close_series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            curr_rsi = rsi.iloc[-1]
            
            # B. 成交量暴增判斷 (今日成交量 > 20日均量 2 倍)
            avg_vol = vol_series.rolling(20).mean().iloc[-1]
            curr_vol = vol_series.iloc[-1]
            vol_spike = curr_vol > (avg_vol * 2)
            
            # C. 趨勢與波段低點 (底底高)
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            if len(low_idx) < 2: continue
            
            curr_price = float(prices[-1])
            ma20 = float(close_series.rolling(20).mean().iloc[-1])
            last_low = float(prices[low_idx[-1]])
            prev_low = float(prices[low_idx[-2]])
            
            # D. 策略篩選：底底高 + 站上 20MA + RSI 不過熱 (<70)
            if last_low > prev_low and curr_price > ma20 and curr_rsi < 70:
                # 買賣建議價位
                support_price = round(last_low, 2)
                buy_min = round(support_price * 1.01, 2)
                buy_max = round(support_price * 1.05, 2)
                take_profit = round(curr_price * 1.15, 2)  # 預設 15% 停利
                stop_loss = round(support_price * 0.97, 2) # 支撐下方 3%
                
                results.append({
                    "股票名稱": s['label'],
                    "代號": s['code'],
                    "現價": round(curr_price, 2),
                    "RSI(14)": round(curr_rsi, 1),
                    "成交量狀態": "🔥 爆量" if vol_spike else "正常",
                    "建議買進區間": f"{buy_min} - {buy_max}",
                    "支撐價位": support_price,
                    "停利目標": take_profit,
                    "停損價位": stop_loss,
                    "風險距離(%)": round((curr_price/support_price-1)*100, 1)
                })
        except:
            continue
    return results

# --- 3. UI 介面 ---
st.title("🛡️ TW 2026 全台股趨勢終極掃描系統")
all_stocks = get_full_taiwan_stock_list()

with st.sidebar:
    st.header("📊 掃描與排序設定")
    # 排序功能
    sort_option = st.selectbox(
        "結果排序方式", 
        ["風險距離(%) 由小到大", "價位由高到低", "價位由低到高", "RSI 強弱"]
    )
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 8, help="較小的值會抓到更細微的轉折")
    start_btn = st.button("🔥 啟動全台股深度掃描")

if start_btn:
    total_count = len(all_stocks)
    chunk_size = 40 
    all_results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with st.spinner("正在進行大數據分析..."):
        for i in range(0, total_count, chunk_size):
            chunk = all_stocks[i : i + chunk_size]
            symbols = [s['symbol'] for s in chunk]
            status_text.text(f"掃描進度: {i} / {total_count}")
            
            try:
                df_batch = yf.download(symbols, period="6mo", progress=False, group_by='ticker', threads=True)
                if not df_batch.empty:
                    chunk_results = analyze_chunk(df_batch, chunk, sens)
                    all_results.extend(chunk_results)
            except:
                pass 
            
            progress_bar.progress(min((i + chunk_size) / total_count, 1.0))
            time.sleep(0.5)

    status_text.text("✅ 掃描完成！")

    if all_results:
        final_df = pd.DataFrame(all_results)
        
        # --- 排序邏輯 ---
        if sort_option == "風險距離(%) 由小到大":
            final_df = final_df.sort_values(by="風險距離(%)")
        elif sort_option == "價位由高到低":
            final_df = final_df.sort_values(by="現價", ascending=False)
        elif sort_option == "價位由低到高":
            final_df = final_df.sort_values(by="現價", ascending=True)
        else:
            final_df = final_df.sort_values(by="RSI(14)", ascending=False)

        st.success(f"🎉 找到 {len(final_df)} 檔符合條件標的。")

        # 視覺化：爆量顯示紅色背景
        def highlight_vol(val):
            color = '#3d1c1c' if val == "🔥 爆量" else ''
            return f'background-color: {color}'

        st.dataframe(
            final_df.style.applymap(highlight_vol, subset=['成交量狀態']), 
            use_container_width=True
        )
    else:
        st.warning("☹️ 目前條件下未發現符合標的。")

st.info("💡 提示：'風險距離' 越小代表現價越靠近支撐點，進場風險相對較低。")
