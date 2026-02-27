import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from scipy.signal import argrelextrema
import numpy as np
import urllib3
import io

# 1. 基礎設定與禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="2026 台股趨勢篩選器", layout="wide")

@st.cache_data(ttl=3600)
def get_all_stocks():
    """抓取上市櫃清單：解決新版 Pandas 解析問題"""
    urls = [
        "https://isin.twse.com.tw", # 上市
        "https://isin.twse.com.tw"  # 上櫃
    ]
    stocks = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for url in urls:
        try:
            # 抓取網頁內容
            res = requests.get(url, headers=headers, verify=False, timeout=15)
            res.encoding = 'big5'
            
            # 使用 io.StringIO 解決 Pandas 2.0+ 的解析警告/錯誤
            html_data = io.StringIO(res.text)
            dfs = pd.read_html(html_data)
            
            if not dfs:
                continue
                
            df = dfs[0]
            # 重新設定標題與清理資料
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            for item in df['有價證券代號及名稱']:
                if '　' in str(item): # 全形空格
                    parts = item.split('　')
                    if len(parts) >= 2:
                        code = parts[0].strip()
                        name = parts[1].strip()
                        # 篩選 4 位數普通股
                        if len(code) == 4:
                            suffix = ".TW" if "strMode=2" in url else ".TWO"
                            stocks.append({"label": f"{code} {name}", "symbol": f"{code}{suffix}"})
        except Exception as e:
            st.error(f"抓取清單時發生錯誤 ({url}): {str(e)}")
            
    return stocks

def analyze_stock(symbol, order):
    """技術分析：底底高 + 站上 20MA"""
    try:
        # 下載資料
        df = yf.download(symbol, period="6mo", progress=False)
        if len(df) < 40:
            return None
        
        # 處理 Close 價格 (相容不同版本的 yfinance)
        if 'Close' in df.columns:
            close_prices = df['Close'].values.flatten()
        else:
            return None
            
        # 尋找局部低點
        low_indices = argrelextrema(close_prices, np.less, order=order)[0]
        if len(low_indices) < 2:
            return None
        
        last_low = float(close_prices[low_indices[-1]])
        prev_low = float(close_prices[low_indices[-2]])
        curr_price = float(close_prices[-1])
        
        # 計算 20 均線
        ma20_series = df['Close'].rolling(window=20).mean()
        ma20 = float(ma20_series.iloc[-1])
        
        # 判斷條件：底底高 且 現價 > 20MA
        if last_low > prev_low and curr_price > ma20:
            return {
                "代號": symbol, 
                "現價": round(curr_price, 2), 
                "最近支撐": round(last_low, 2), 
                "強度幅度": f"{round((curr_price/last_low-1)*100,1)}%"
            }
    except Exception:
        return None
    return None

# --- UI 介面 ---
st.title("🇹🇼 TW 2026 台股趨勢自動掃描系統")
st.info("系統邏輯：自動篩選底底高 (Higher Lows) 且股價站上 20MA 的個股。")

# 側邊欄設定
with st.sidebar:
    st.header("設定參數")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 10, help="數字越大，找出的低點越具代表性")
    limit = st.number_input("掃描數量 (建議 50-100)", 10, 1000, 50)
    start_btn = st.button("🚀 開始掃描全台股")

# 點擊按鈕後的行為
if start_btn:
    with st.spinner("正在初始化股票清單..."):
        all_stocks = get_all_stocks()
    
    if not all_stocks:
        st.error("❌ 無法取得股票清單。請檢查網路連線或稍後再試。")
    else:
        # 依照使用者設定的數量進行掃描
        num_to_scan = min(len(all_stocks), int(limit))
        stock_list = all_stocks[:num_to_scan]
        
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, stock in enumerate(stock_list):
            status_text.text(f"🔍 正在分析 ({i+1}/{num_to_scan}): {stock['label']}")
            res = analyze_stock(stock['symbol'], sens)
            if res:
                res['名稱'] = stock['label']
                results.append(res)
            progress_bar.progress((i+1)/num_to_scan)
        
        status_text.text("✅ 掃描任務完成！")
        
        if results:
            final_df = pd.DataFrame(results)
            # 整理欄位順序
            final_df = final_df[['名稱', '代號', '現價', '最近支撐', '強度幅度']]
            st.success(f"🎉 找到 {len(final_df)} 檔符合條件標的！")
            st.dataframe(final_df, use_container_width=True)
        else:
            st.warning("☹️ 目前範圍內沒有符合條件的標的，請嘗試調整靈敏度或增加掃描數量。")
