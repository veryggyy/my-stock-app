import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import time
import os

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="2026 台股趨勢回測掃描系統", layout="wide")

@st.cache_data(ttl=86400)
def get_full_taiwan_stock_list():
    cache_file = "taiwan_stock_list.csv"
    if os.path.exists(cache_file):
        try:
            df = pd.read_csv(cache_file, dtype=str)
            df.columns = [c.strip() for c in df.columns]
            for col in df.columns:
                df[col] = df[col].str.strip().str.strip(',')
            if 'symbol' not in df.columns and 'code' in df.columns:
                df['symbol'] = df['code'] + ".TW"
            return df.to_dict('records')
        except: pass
    return [{"label": "台積電", "code": "2330", "symbol": "2330.TW"}]

# --- 2. 核心分析邏輯 (含回測計算) ---
def analyze_with_backtest(df_batch, selected_stocks_chunk, order):
    results = []
    backtest_days = 30 # 模擬 30 天前的買入訊號
    
    for s in selected_stocks_chunk:
        symbol = s['symbol']
        try:
            if symbol not in df_batch: continue
            data = df_batch[symbol].dropna()
            if len(data) < 60: continue # 需要更多數據來支撐回測
            
            # --- 當前即時分析 ---
            close_series = data['Close']
            prices = close_series.values
            curr_price = float(prices[-1])
            ma20 = float(close_series.rolling(20).mean().iloc[-1])
            
            # 尋找底底高型態
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            if len(low_idx) < 2: continue
            last_low = float(prices[low_idx[-1]])
            prev_low = float(prices[low_idx[-2]])
            
            # --- 30天前模擬回測邏輯 ---
            # 取得 30 天前的數據切片
            hist_data = data.iloc[:-backtest_days]
            if len(hist_data) > 40:
                hist_prices = hist_data['Close'].values
                h_low_idx = argrelextrema(hist_prices, np.less, order=order)[0]
                
                sim_return = "N/A"
                if len(h_low_idx) >= 2:
                    h_last_low = float(hist_prices[h_low_idx[-1]])
                    h_prev_low = float(hist_prices[h_low_idx[-2]])
                    h_curr_price = float(hist_prices[-1])
                    h_ma20 = float(hist_data['Close'].rolling(20).mean().iloc[-1])
                    
                    # 如果 30 天前符合買入條件
                    if h_last_low > h_prev_low and h_curr_price > h_ma20:
                        ret = (curr_price / h_curr_price - 1) * 100
                        sim_return = f"{round(ret, 1)}%"

            # 篩選當前符合條件者
            if last_low > prev_low and curr_price > ma20:
                # 去掉尾數 .0 的處理
                fmt_price = int(curr_price) if curr_price % 1 == 0 else round(curr_price, 2)
                fmt_support = int(last_low) if last_low % 1 == 0 else round(last_low, 2)
                
                results.append({
                    "股票名稱": s['label'],
                    "代號": s['code'],
                    "現價": fmt_price,
                    "支撐價": fmt_support,
                    "風險距離%": round((curr_price/last_low-1)*100, 1),
                    "30日模擬報酬": sim_return,
                    "成交量狀態": "🔥 爆量" if data['Volume'].iloc[-1] > data['Volume'].rolling(20).mean().iloc[-1]*2 else "正常"
                })
        except: continue
    return results

# --- 3. UI 介面 ---
st.title("📊 TW 2026 趨勢掃描與回測系統")
all_stocks = get_full_taiwan_stock_list()

with st.sidebar:
    st.header("⚙️ 參數設定")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 8)
    st.write(f"當前清單共: {len(all_stocks)} 檔")
    start_btn = st.button("🚀 開始深度分析與回測")

if start_btn:
    total_count = len(all_stocks)
    chunk_size = 30
    all_results = []
    progress_bar = st.progress(0)
    
    with st.spinner("正在執行歷史回測與即時掃描..."):
        for i in range(0, total_count, chunk_size):
            chunk = all_stocks[i : i + chunk_size]
            symbols = [s['symbol'] for s in chunk]
            try:
                df_batch = yf.download(symbols, period="1y", progress=False, group_by='ticker')
                if not df_batch.empty:
                    all_results.extend(analyze_with_backtest(df_batch, chunk, sens))
            except: pass
            progress_bar.progress(min((i + chunk_size) / total_count, 1.0))
            time.sleep(0.5)

    if all_results:
        df = pd.DataFrame(all_results)
        
        # --- 數據呈現優化 ---
        # 1. 統計回測數據
        valid_rets = [float(x.strip('%')) for x in df["30日模擬報酬"] if x != "N/A"]
        if valid_rets:
            win_rate = len([x for x in valid_rets if x > 0]) / len(valid_rets) * 100
            avg_ret = sum(valid_rets) / len(valid_rets)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("模擬回測標的數", f"{len(valid_rets)} 檔")
            c2.metric("30日平均勝率", f"{round(win_rate, 1)}%")
            c3.metric("30日平均報酬", f"{round(avg_ret, 2)}%")
            st.divider()

        # 2. 顯示表格 (去掉尾數 .0)
        st.success(f"發現 {len(df)} 檔當前符合型態標的")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("查無符合標的。")

st.caption("註：'30日模擬報酬' 指的是如果 30 天前該股也符合同樣的底底高條件，持有到今天的漲跌幅。")
