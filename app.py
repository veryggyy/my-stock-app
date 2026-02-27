import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from scipy.signal import argrelextrema
import numpy as np
import urllib3

# 禁用 SSL 安全警告 (解決 SSL 憑證驗證失敗的問題)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 頁面設定
st.set_page_config(page_title="2026 台股趨勢篩選器", layout="wide")

@st.cache_data(ttl=3600)
def get_all_stocks():
    """修正版：解決 SSL 錯誤並抓取正確的上市櫃清單"""
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
            # 加入 verify=False 解決截圖中的 SSL 錯誤
            res = requests.get(url, headers=headers, verify=False, timeout=15)
            res.encoding = 'big5' # 台股網站必備編碼
            
            dfs = pd.read_html(res.text)
            if not dfs: continue
            df = dfs[0]
            
            # 重新設定標題列
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            for item in df['有價證券代號及名稱']:
                if '　' in str(item): # 全形空格分割
                    parts = item.split('　')
                    code = parts[0].strip()
                    name = parts[1].strip()
                    # 篩選 4 位數普通股 (排除權證、ETF)
                    if len(code) == 4:
                        suffix = ".TW" if "strMode=2" in url else ".TWO"
                        stocks.append({"label": f"{code} {name}", "symbol": f"{code}{suffix}"})
        except Exception as e:
            st.error(f"網址 {url} 抓取失敗: {str(e)}")
            
    return stocks

def analyze_stock(symbol, order):
    """技術分析邏輯：底底高 + 站上 20MA"""
    try:
        # 下載最近 6 個月的資料
        df = yf.download(symbol, period="6mo", progress=False)
        if len(df) < 40: return None
        
        # 處理 yfinance 可能回傳的多層索引 (MultiIndex)
        if isinstance(df.columns, pd.MultiIndex):
            close_prices = df['Close'][symbol].values.flatten()
        else:
            close_prices = df['Close'].values.flatten()
            
        # 尋找局部低點
        low_indices = argrelextrema(close_prices, np.less, order=order)[0]
        if len(low_indices) < 2: return None
        
        last_low = close_prices[low_indices[-1]]
        prev_low = close_prices[low_indices[-2]]
        curr_price = close_prices[-1]
        
        # 計算 20 均線 (MA20)
        ma20_series = df['Close'].rolling(window=20).mean()
        if isinstance(ma20_series, pd.DataFrame):
            ma20 = ma20_series[symbol].iloc[-1]
        else:
            ma20 = ma20_series.iloc[-1]
        
        # 條件判斷：底底高 (最新低點 > 前一低點) 且 現價 > MA20
        if last_low > prev_low and curr_price > ma20:
            return {
                "代號": symbol, 
                "現價": round(float(curr_price), 2), 
                "最近支撐": round(float(last_low), 2), 
                "強度幅度": f"{round((float(curr_price)/float(last_low)-1)*100,1)}%"
            }
    except:
        return None
    return None

# --- UI 介面 ---
st.title("🇹🇼 TW 2026 台股趨勢自動掃描系統")
st.info("系統邏輯：自動篩選底底高 (Higher Lows) 且股價站上 20MA 的個股。")

with st.sidebar:
    st.header("設定參數")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 10, help="數字越大，找出的轉折點越顯著")
    limit = st.number_input("掃描數量 (建議 50-100)", 10, 1000, 50)
    start_btn = st.button("🚀 開始掃描全台股")

if start_btn:
    all_stocks = get_all_stocks()
    
    if not all_stocks:
        st.error("無法取得股票清單。請確認您的網路連線，或稍後再試。")
    else:
        # 取使用者設定的掃描數量
        stock_list = all_stocks[:int(limit)]
        results = []
        
        # 進度條與狀態文字
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, stock in enumerate(stock_list):
            status_text.text(f"正在分析 ({i+1}/{len(stock_list)}): {stock['label']}")
            res = analyze_stock(stock['symbol'], sens)
            if res:
                res['名稱'] = stock['label']
                results.append(res)
            progress_bar.progress((i+1)/len(stock_list))
        
        status_text.text("✅ 掃描完成！")
        
        if results:
            final_df = pd.DataFrame(results)
            st.success(f"🎉 找到 {len(final_df)} 檔符合條件的強勢個股！")
            # 調整欄位順序
            final_df = final_df[['名稱', '代號', '現價', '最近支撐', '強度幅度']]
            st.dataframe(final_df, use_container_width=True)
        else:
            st.warning("☹️ 目前範圍內沒有找到符合條件的標的，建議調整靈敏度或增加掃描數量。")

