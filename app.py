import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import time
import os

# --- 1. 頁面基礎設定 (必須在所有 st 指令之前) ---
st.set_page_config(page_title="2026 台股趨勢回測掃描系統", layout="wide")

@st.cache_data(ttl=86400)
def get_full_taiwan_stock_list():
    """自動處理 CSV 欄位名稱與多餘逗號，並修正 symbol 格式"""
    cache_file = "taiwan_stock_list.csv"
    if os.path.exists(cache_file):
        try:
            # 讀取 CSV
            df = pd.read_csv(cache_file, dtype=str)
            
            # 清除欄位名稱的空白與逗號 (解決 KeyError: 'symbol')
            df.columns = [c.strip().replace(',', '') for c in df.columns]
            
            # 清理資料內容 (解決 如 '1101,' 這種尾隨逗號問題)
            for col in df.columns:
                df[col] = df[col].str.strip().str.strip(',')
                
            # 自動補齊 symbol 欄位 (確保 yfinance 能讀取)
            if 'symbol' not in df.columns and 'code' in df.columns:
                df['symbol'] = df['code'] + ".TW"
            if 'label' not in df.columns:
                df['label'] = df.get('code', '未知股票')
                
            return df.to_dict('records')
        except Exception as e:
            st.error(f"讀取 CSV 失敗: {e}")
            
    # 保底資料 (若 CSV 讀取失敗時顯示)
    return [{"label": "台積電", "code": "2330", "symbol": "2330.TW"}]

def format_num(val):
    """自定義格式化：去掉數值尾數的 .0"""
    if pd.isna(val): return ""
    try:
        f_val = float(val)
        return int(f_val) if f_val % 1 == 0 else round(f_val, 2)
    except:
        return val

# --- 2. 核心分析與回測邏輯 ---
def analyze_with_backtest(df_batch, selected_stocks_chunk, order):
    results = []
    backtest_days = 30 # 模擬 30 天前買入後的表現
    
    for s in selected_stocks_chunk:
        symbol = s['symbol']
        try:
            if symbol not in df_batch: continue
            data = df_batch[symbol].dropna()
            if len(data) < 60: continue
            
            # A. 當前狀態分析
            close_series = data['Close']
            prices = close_series.values
            curr_price = float(prices[-1])
            ma20 = float(close_series.rolling(20).mean().iloc[-1])
            
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            if len(low_idx) < 2: continue
            last_low = float(prices[low_idx[-1]])
            prev_low = float(prices[low_idx[-2]])
            
            # B. 30天前歷史回測
            hist_data = data.iloc[:-backtest_days]
            sim_return = "N/A"
            if len(hist_data) > 40:
                h_prices = hist_data['Close'].values
                h_low_idx = argrelextrema(h_prices, np.less, order=order)[0]
                if len(h_low_idx) >= 2:
                    h_last_low = h_prices[h_low_idx[-1]]
                    h_prev_low = h_prices[h_low_idx[-2]]
                    h_ma20 = hist_data['Close'].rolling(20).mean().iloc[-1]
                    # 如果 30 天前符合「底底高 + 站上 20MA」
                    if h_last_low > h_prev_low and h_prices[-1] > h_ma20:
                        ret = (curr_price / h_prices[-1] - 1) * 100
                        sim_return = f"{round(ret, 1)}%"

            # C. 篩選當前符合條件者
            if last_low > prev_low and curr_price > ma20:
                results.append({
                    "股票名稱": s['label'],
                    "代號": s['code'],
                    "現價": format_num(curr_price),
                    "支撐價": format_num(last_low),
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
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 8, help="靈敏度越小，抓到的轉折越細微")
    st.info(f"當前清單共: {len(all_stocks)} 檔")
    start_btn = st.button("🚀 開始深度掃描與歷史回測")

if start_btn:
    total_count = len(all_stocks)
    chunk_size = 30
    all_results = []
    progress_bar = st.progress(0)
    
    with st.spinner("正在下載大數據並執行 30 日歷史回測..."):
        for i in range(0, total_count, chunk_size):
            chunk = all_stocks[i : i + chunk_size]
            symbols = [s['symbol'] for s in chunk]
            try:
                # 下載一年份資料以支撐回測計算
                df_batch = yf.download(symbols, period="1y", progress=False, group_by='ticker')
                if not df_batch.empty:
                    all_results.extend(analyze_with_backtest(df_batch, chunk, sens))
            except: pass
            progress_bar.progress(min((i + chunk_size) / total_count, 1.0))
            time.sleep(0.5)

    if all_results:
        df = pd.DataFrame(all_results)
        
        # 績效總結看板
        valid_rets = [float(x.replace('%','')) for x in df["30日模擬報酬"] if x != "N/A"]
        if valid_rets:
            st.subheader("📈 近 30 日策略績效驗證")
            c1, c2, c3 = st.columns(3)
            win_rate = len([x for x in valid_rets if x > 0]) / len(valid_rets) * 100
            avg_ret = sum(valid_rets) / len(valid_rets)
            c1.metric("模擬標的數", f"{len(valid_rets)} 檔")
            c2.metric("平均勝率", f"{round(win_rate, 1)}%")
            c3.metric("平均報酬", f"{round(avg_ret, 2)}%")
            st.divider()

        st.success(f"🎉 發現 {len(df)} 檔當前符合型態標的")
        
        # 預設依「風險距離」排序，越小代表離支撐越近
        df = df.sort_values(by="風險距離%")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("☹️ 目前條件下未發現符合標的。")

st.caption("💡 註：'30日模擬報酬' 指 30 天前若符合同樣條件，持有至今的績效。價位已自動去除尾數 .0。")
