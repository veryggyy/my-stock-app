import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import time
import os

# --- 1. 頁面設定 ---
st.set_page_config(page_title="2026 台股趨勢回測掃描系統", layout="wide")

@st.cache_data(ttl=3600)
def get_full_taiwan_stock_list():
    cache_file = "taiwan_stock_list.csv"
    if os.path.exists(cache_file):
        try:
            df = pd.read_csv(cache_file, dtype=str)
            df.columns = [c.strip() for c in df.columns]
            code_col = next((c for c in df.columns if 'code' in c.lower() or '代號' in c), df.columns[0])
            label_col = next((c for c in df.columns if 'label' in c.lower() or '名稱' in c or '股票' in c), df.columns[0])
            
            stocks = []
            for _, row in df.iterrows():
                code = str(row[code_col]).strip().replace(".TW", "").replace(".TWO", "")
                name = str(row[label_col]).strip()
                # 預設嘗試 .TW (上市)，若掃描不到可在此邏輯調整
                stocks.append({"label": name, "code": code, "symbol": f"{code}.TW"})
            return stocks
        except: pass
    return [{"label": "台積電", "code": "2330", "symbol": "2330.TW"}]

# --- 2. 核心分析邏輯 ---
def analyze_stock(data, order):
    """分析單一股票數據"""
    prices = data['Close'].values.astype(float)
    if len(prices) < 60: return None
    
    curr_price = float(prices[-1])
    ma20 = data['Close'].rolling(20).mean().iloc[-1]
    
    # 尋找低點 (底底高型態)
    low_idx = argrelextrema(prices, np.less, order=order)[0]
    if len(low_idx) < 2: return None
    
    last_low, prev_low = prices[low_idx[-1]], prices[low_idx[-2]]
    
    # 條件：最近一個低點比前一個高，且現價大於月線 98%
    if last_low > prev_low and curr_price > (ma20 * 0.98):
        return {
            "現價": round(curr_price, 2),
            "支撐價": round(last_low, 2),
            "風險距離%": round((curr_price/last_low-1)*100, 1),
            "成交量狀態": "🔥 爆量" if data['Volume'].iloc[-1] > data['Volume'].rolling(20).mean().iloc[-1]*1.5 else "正常"
        }
    return None

# --- 3. UI 介面 ---
st.title("🛡️ TW 2026 趨勢掃描與回測系統")
all_stocks = get_full_taiwan_stock_list()

with st.sidebar:
    st.header("⚙️ 參數設定")
    sens = st.slider("趨勢靈敏度 (Order)", 3, 15, 5)
    st.info(f"📊 當前清單共: {len(all_stocks)} 檔")
    start_btn = st.button("🚀 啟動完整掃描")

if start_btn:
    all_results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 為確保穩定，每 10 檔暫停一次，避免被 Yahoo 封鎖
    for idx, s in enumerate(all_stocks):
        symbol = s['symbol']
        status_text.text(f"正在分析 ({idx+1}/{len(all_stocks)}): {s['label']} ({symbol})")
        
        try:
            # 逐檔下載，確保資料完整性
            data = yf.download(symbol, period="6mo", progress=False, auto_adjust=True)
            if not data.empty:
                res = analyze_stock(data, sens)
                if res:
                    res.update({"股票名稱": s['label'], "代號": s['code']})
                    all_results.append(res)
        except:
            pass
            
        progress_bar.progress((idx + 1) / len(all_stocks))
        if (idx + 1) % 15 == 0: time.sleep(0.5) # 每15檔休息半秒

    status_text.empty()
    
    if all_results:
        df = pd.DataFrame(all_results)
        st.success(f"掃描完畢！發現 {len(df)} 檔符合型態標的")
        st.dataframe(df.sort_values(by="風險距離%"), use_container_width=True)
    else:
        st.error("掃描完成，但沒有標的符合「底底高」型態。請嘗試調低靈敏度。")

st.markdown("---")
st.caption("註：單檔掃描速度較慢，請保持視窗開啟直到進度條完成。")
