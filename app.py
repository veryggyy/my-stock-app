import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import os
from concurrent.futures import ThreadPoolExecutor

# --- 1. 頁面設定 ---
st.set_page_config(page_title="2026 台股極速掃描系統", layout="wide")

@st.cache_data(ttl=3600)
def get_stock_list():
    cache_file = "taiwan_stock_list.csv"
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file, dtype=str)
        df.columns = [c.strip() for c in df.columns]
        code_col = next((c for c in df.columns if '代號' in c or 'code' in c), df.columns[0])
        name_col = next((c for c in df.columns if '名稱' in c or 'label' in c), df.columns[0])
        # 批量生成代碼：優先嘗試 .TW，並過濾掉非四位數的權證/存託憑證
        df = df[df[code_col].str.len() == 4] 
        return {f"{row[code_col]}.TW": row[name_col] for _, row in df.iterrows()}
    return {"2330.TW": "台積電"}

# --- 2. 高速核心分析 ---
def fast_analyze(symbol, name, data, order):
    try:
        if len(data) < 40: return None
        prices = data['Close'].values.astype(float)
        ma20 = data['Close'].rolling(20).mean().iloc[-1]
        curr_price = prices[-1]

        # 尋找低點 (底底高)
        low_idx = argrelextrema(prices, np.less, order=order)[0]
        if len(low_idx) < 2: return None
        
        last_low, prev_low = prices[low_idx[-1]], prices[low_idx[-2]]

        # 放寬條件：底底高 + 價格在月線附近 (上下 5% 均可)
        if last_low > prev_low and curr_price > (ma20 * 0.95):
            return {
                "股票名稱": name, "代號": symbol.split('.')[0],
                "現價": round(curr_price, 2), "支撐價": round(last_low, 2),
                "風險距離%": round((curr_price/last_low-1)*100, 1),
                "成交量狀態": "🔥 爆量" if data['Volume'].iloc[-1] > data['Volume'].rolling(20).mean().iloc[-1]*1.5 else "正常"
            }
    except: return None
    return None

# --- 3. UI 介面 ---
st.title("⚡ TW 2026 極速趨勢掃描器")
stock_dict = get_stock_list()
symbols = list(stock_dict.keys())

with st.sidebar:
    st.header("⚙️ 參數設定")
    sens = st.slider("趨勢靈敏度 (Order)", 2, 10, 4)
    st.info(f"📊 待掃描清單: {len(symbols)} 檔")
    start_btn = st.button("🚀 啟動極速掃描")

if start_btn:
    all_results = []
    progress_bar = st.progress(0)
    
    with st.spinner(f"正在並行下載 {len(symbols)} 檔數據..."):
        # 使用 yfinance 內建的多執行緒批量下載 (最快的方式)
        raw_data = yf.download(symbols, period="6mo", group_by='ticker', threads=True, progress=False)
        
        # 進行多線程分析處理
        for idx, (sym, name) in enumerate(stock_dict.items()):
            try:
                # 處理 yfinance 可能回傳的單/多層 Index 結構
                df = raw_data[sym].dropna() if len(symbols) > 1 else raw_data.dropna()
                res = fast_analyze(sym, name, df, sens)
                if res: all_results.append(res)
            except: continue
            if idx % 100 == 0: progress_bar.progress((idx+1)/len(symbols))

    if all_results:
        st.success(f"掃描完畢！耗時極短，共發現 {len(all_results)} 檔符合型態標的")
        st.dataframe(pd.DataFrame(all_results).sort_values(by="風險距離%"), use_container_width=True)
    else:
        st.warning("查無符合標的。建議嘗試將「靈敏度」調至 2 或 3。")

st.markdown("---")
st.caption("優化重點：採用 yfinance Threads 模式下載，並加入 4 位數代碼過濾以提升精準度。")
