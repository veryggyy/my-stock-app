import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from scipy.signal import argrelextrema
import numpy as np
import plotly.graph_objects as go

# 頁面設定
st.set_page_config(page_title="2026 台股趨勢篩選器", layout="wide")

@st.cache_data(ttl=3600)
def get_all_stocks():
    """自動抓取 2026 年最新上市櫃清單"""
    urls = ["https://isin.twse.com.tw", 
            "https://isin.twse.com.tw"]
    stocks = []
    for url in urls:
        res = requests.get(url)
        df = pd.read_html(res.text)[0]
        df.columns = df.iloc[0]
        for item in df['有價證券代號及名稱'].iloc[1:]:
            if '　' in str(item):
                code, name = item.split('　')
                if len(code) == 4:
                    suffix = ".TW" if "Mode=2" in url else ".TWO"
                    stocks.append({"label": f"{code} {name}", "symbol": f"{code}{suffix}"})
    return stocks

def analyze_stock(symbol, order):
    """技術分析邏輯：底底高 + 站上月線"""
    df = yf.download(symbol, period="6mo", progress=False)
    if len(df) < 40: return None
    close = df['Close'].values.flatten()
    low_idx = argrelextrema(close, np.less, order=order)[0]
    if len(low_idx) < 2: return None
    
    last_low, prev_low = close[low_idx[-1]], close[low_idx[-2]]
    curr_price = close[-1]
    ma20 = df['Close'].rolling(20).mean().iloc[-1].item()
    
    if last_low > prev_low and curr_price > ma20:
        return {"代號": symbol, "現價": round(curr_price, 2), "最近支撐": round(last_low, 2), "幅度": f"{round((curr_price/last_low-1)*100,1)}%"}
    return None

# --- UI 介面 ---
st.title("🇹🇼 2026 台股趨勢自動掃描系統")
st.markdown("本系統自動篩選**底底高 (Higher Lows)** 且站上 **20MA** 的強勢個股。")

with st.sidebar:
    st.header("設定參數")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 10)
    limit = st.number_input("掃描數量 (建議 50-100)", 10, 500, 50)
    start_btn = st.button("🚀 開始掃描全台股")

if start_btn:
    stock_list = get_all_stocks()[:limit]
    results = []
    bar = st.progress(0)
    for i, s in enumerate(stock_list):
        res = analyze_stock(s['symbol'], sens)
        if res: 
            res['名稱'] = s['label']
            results.append(res)
        bar.progress((i+1)/len(stock_list))
    
    if results:
        final_df = pd.DataFrame(results)
        st.success(f"找到 {len(final_df)} 檔符合條件標的！")
        st.dataframe(final_df, use_container_width=True)
        
        # 下載 Excel/CSV
        csv = final_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 下載篩選報表", csv, "stocks.csv", "text/csv")
    else:
        st.warning("目前範圍內無符合條件股票。")
