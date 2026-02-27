import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from scipy.signal import argrelextrema
import numpy as np

# 頁面設定
st.set_page_config(page_title="2026 台股趨勢篩選器", layout="wide")

@st.cache_data(ttl=3600)
def get_all_stocks():
    """修正後的自動抓取上市櫃清單邏輯"""
    # 完整的證交所與櫃買中心 ISIN 查詢網址
    urls = [
        "https://isin.twse.com.tw", # 上市
        "https://isin.twse.com.tw"  # 上櫃
    ]
    stocks = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    for url in urls:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.encoding = 'big5' # 關鍵：台股 ISIN 頁面使用 big5 編碼
            
            # 抓取表格
            dfs = pd.read_html(res.text)
            if not dfs: continue
            df = dfs[0]
            
            # 清理資料：第一列通常是標題
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            for item in df['有價證券代號及名稱']:
                if '　' in str(item): # 注意：這裡是全形空格
                    parts = item.split('　')
                    if len(parts) >= 2:
                        code, name = parts[0], parts[1]
                        if len(code) == 4: # 篩選普通股
                            suffix = ".TW" if "strMode=2" in url else ".TWO"
                            stocks.append({"label": f"{code} {name}", "symbol": f"{code}{suffix}"})
        except Exception as e:
            st.warning(f"網址 {url} 抓取失敗: {e}")
            
    return stocks

def analyze_stock(symbol, order):
    """技術分析邏輯：底底高 + 站上月線"""
    try:
        df = yf.download(symbol, period="6mo", progress=False)
        if len(df) < 40: return None
        
        # 確保資料為 1D 陣列
        close = df['Close'].values.flatten()
        # 尋找局部低點
        low_idx = argrelextrema(close, np.less, order=order)[0]
        if len(low_idx) < 2: return None
        
        last_low = close[low_idx[-1]]
        prev_low = close[low_idx[-2]]
        curr_price = close[-1]
        
        # 計算 20MA
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        if isinstance(ma20, pd.Series): ma20 = ma20.iloc[0]
        
        # 判斷條件：最近一個低點大於前一個低點 (底底高) 且 收盤 > 20MA
        if last_low > prev_low and curr_price > ma20:
            return {
                "代號": symbol, 
                "現價": round(float(curr_price), 2), 
                "最近支撐": round(float(last_low), 2), 
                "幅度": f"{round((float(curr_price)/float(last_low)-1)*100,1)}%"
            }
    except:
        return None
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
    all_stocks = get_all_stocks()
    if not all_stocks:
        st.error("無法取得股票清單，請檢查網路或來源網站。")
    else:
        stock_list = all_stocks[:limit]
        results = []
        bar = st.progress(0)
        status_text = st.empty()
        
        for i, s in enumerate(stock_list):
            status_text.text(f"正在分析 ({i+1}/{len(stock_list)}): {s['label']}")
            res = analyze_stock(s['symbol'], sens)
            if res: 
                res['名稱'] = s['label']
                results.append(res)
            bar.progress((i+1)/len(stock_list))
        
        status_text.text("掃描完成！")
        if results:
            final_df = pd.DataFrame(results)
            st.success(f"找到 {len(final_df)} 檔符合條件標的！")
            st.dataframe(final_df, use_container_width=True)
        else:
            st.info("目前的設定範圍內沒有找到符合條件的標的。")

