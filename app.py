import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from scipy.signal import argrelextrema
import numpy as np
import urllib3
import io

# 基礎設定
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="2026 台股趨勢篩選器", layout="wide")

@st.cache_data(ttl=3600)
def get_all_stocks():
    """抓取股票清單：包含官網抓取與 GitHub 備援方案"""
    stocks = []
    # 方案 A: 官網抓取 (加上更強的 Headers)
    urls = [
        "https://isin.twse.com.tw", # 上市
        "https://isin.twse.com.tw"  # 上櫃
    ]
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,/ ;q=0.8'
    }
    
    for url in urls:
        try:
            res = requests.get(url, headers=headers, verify=False, timeout=10)
            res.encoding = 'big5'
            html_io = io.StringIO(res.text)
            dfs = pd.read_html(html_io)
            if dfs:
                df = dfs[0]
                df.columns = df.iloc[0]
                for item in df['有價證券代號及名稱'].iloc[1:]:
                    if '　' in str(item):
                        parts = item.split('　')
                        code = parts[0].strip()
                        name = parts[1].strip()
                        if len(code) == 4:
                            suffix = ".TW" if "strMode=2" in url else ".TWO"
                            stocks.append({"label": f"{code} {name}", "symbol": f"{code}{suffix}"})
        except Exception:
            continue # 如果官網失敗，嘗試下一組或進入備援
            
    # 方案 B: 如果官網沒抓到，使用 GitHub 靜態備援 (確保系統不崩潰)
    if not stocks:
        try:
            # 這裡使用一個常用的台股清單備援連結
            backup_url = "https://raw.githubusercontent.com"
            backup_df = pd.read_csv(backup_url)
            for _, row in backup_df.iterrows():
                code = str(row['stock_id'])
                name = str(row['stock_name'])
                if len(code) == 4:
                    suffix = ".TW" if row['type'] == 'twse' else ".TWO"
                    stocks.append({"label": f"{code} {name}", "symbol": f"{code}{suffix}"})
        except:
            pass
            
    return stocks

def analyze_stock(symbol, order):
    """技術分析：底底高 + 站上 20MA"""
    try:
        df = yf.download(symbol, period="6mo", progress=False, multi_level_index=False)
        if len(df) < 40: return None
        
        # 確保抓到 Close 價格
        close_prices = df['Close'].values.flatten()
        
        # 尋找局部低點
        low_indices = argrelextrema(close_prices, np.less, order=order)[0]
        if len(low_indices) < 2: return None
        
        last_low = float(close_prices[low_indices[-1]])
        prev_low = float(close_prices[low_indices[-2]])
        curr_price = float(close_prices[-1])
        
        # 20MA
        ma20 = float(df['Close'].rolling(window=20).mean().iloc[-1])
        
        if last_low > prev_low and curr_price > ma20:
            return {
                "代號": symbol, 
                "現價": round(curr_price, 2), 
                "最近支撐": round(last_low, 2), 
                "強度幅度": f"{round((curr_price/last_low-1)*100,1)}%"
            }
    except:
        return None
    return None

# --- UI 介面 ---
st.title("🇹🇼 TW 2026 台股趨勢自動掃描系統")
st.info("系統邏輯：自動篩選底底高 (Higher Lows) 且股價站上 20MA 的個股。")

with st.sidebar:
    st.header("設定參數")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 10)
    limit = st.number_input("掃描數量", 10, 1000, 50)
    start_btn = st.button("🚀 開始掃描全台股")

if start_btn:
    with st.spinner("正在取得股票清單..."):
        all_stocks = get_all_stocks()
    
    if not all_stocks:
        st.error("❌ 無法取得股票清單。請檢查網路連線。")
    else:
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
        
        status_text.text("✅ 掃描完成！")
        if results:
            final_df = pd.DataFrame(results)
            st.success(f"🎉 找到 {len(final_df)} 檔符合條件標的！")
            st.dataframe(final_df[['名稱', '代號', '現價', '最近支撐', '強度幅度']], use_container_width=True)
        else:
            st.warning("☹️ 目前範圍內沒有符合條件的標的。")
