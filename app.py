import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import time
import ssl
import requests
from io import StringIO

# --- 核心修復：環境安全設定 ---
ssl._create_default_https_context = ssl._create_unverified_context
requests.packages.urllib3.disable_warnings()

st.set_page_config(page_title="2026 全台股趨勢終極掃描器", layout="wide")

@st.cache_data(ttl=86400)
def get_full_taiwan_stock_list():
    """
    優化版：模擬真實 Chrome 請求，解決 No tables found 報錯。
    """
    stocks = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
    }
    
    # 修正後的證交所公開清單 URL
    urls = [
        ("https://isin.twse.com.tw", ".TW"),  # 上市
        ("https://isin.twse.com.tw", ".TWO") # 上櫃
    ]
    
    try:
        for url, suffix in urls:
            response = requests.get(url, headers=headers, timeout=20)
            response.encoding = 'big5'
            
            # 抓取表格，通常第一個表格即為股票清單
            df_list = pd.read_html(StringIO(response.text))
            if not df_list: continue
            
            df = df_list[0]
            # 重新設定欄位名稱
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            # 過濾股票代號 (只取 4 碼純數字普通股)
            for item in df['有價證券代號及名稱'].dropna():
                parts = item.replace('　', ' ').split(' ')
                if len(parts) >= 2:
                    code, name = parts[0], parts[1]
                    if len(code) == 4 and code.isdigit():
                        stocks.append({"label": name, "code": code, "symbol": f"{code}{suffix}"})
            time.sleep(1) # 避免過快請求
            
        return stocks
    except Exception as e:
        st.error(f"清單獲取失敗: {e}")
        return []

def analyze_chunk(df_batch, selected_stocks_chunk, order):
    """分析邏輯：底底高 + 站上 20MA"""
    results = []
    if df_batch is None or df_batch.empty:
        return results

    for s in selected_stocks_chunk:
        symbol = s['symbol']
        try:
            # 針對 yfinance 下載的多重索引進行處理
            if symbol not in df_batch: continue
            series = df_batch[symbol]['Close'].dropna()
            
            if len(series) < 40: continue
            
            prices = series.values
            # 尋找波段低點
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            
            if len(low_idx) < 2: continue
            
            last_low = float(prices[low_idx[-1]])
            prev_low = float(prices[low_idx[-2]])
            curr_price = float(prices[-1])
            ma20 = float(series.rolling(20).mean().iloc[-1])
            
            # 篩選條件：最新低點墊高 且 現價高於 20MA
            if last_low > prev_low and curr_price > ma20:
                results.append({
                    "股票名稱": s['label'],
                    "代號": s['code'],
                    "現價": round(curr_price, 2),
                    "支撐價位": round(last_low, 2),
                    "趨勢偏離": f"{round((curr_price/last_low-1)*100, 1)}%"
                })
        except:
            continue
    return results

# --- UI 介面 ---
st.title("🛡️ TW 2026 全台股趨勢終極掃描系統")
st.markdown("系統將分析全台股，尋找具備**趨勢轉強 (底底高)** 訊號的標的。")

with st.sidebar:
    st.header("掃描設定")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 8, help="建議設為 8-10")
    st.info("💡 預計需 3-5 分鐘，請勿關閉分頁。")
    start_btn = st.button("🔥 啟動全台股深度掃描")

if start_btn:
    all_stocks = get_full_taiwan_stock_list()
    
    if not all_stocks:
        st.error("無法載入股票清單，可能被伺服器暫時阻擋，請稍後再試。")
    else:
        total_count = len(all_stocks)
        chunk_size = 40 
        all_results = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.spinner("正在下載並分析股價大數據..."):
            for i in range(0, total_count, chunk_size):
                chunk = all_stocks[i : i + chunk_size]
                symbols = [s['symbol'] for s in chunk]
                
                status_text.text(f"掃描進度: {i} / {total_count} 檔個股")
                
                try:
                    # 使用 group_by='ticker' 是下載多股最穩定的方式
                    df_batch = yf.download(symbols, period="6mo", progress=False, group_by='ticker', threads=True)
                    chunk_results = analyze_chunk(df_batch, chunk, sens)
                    all_results.extend(chunk_results)
                except Exception:
                    pass 
                
                progress_bar.progress(min((i + chunk_size) / total_count, 1.0))
                time.sleep(0.5) # 防止 IP 被鎖

        status_text.text("✅ 全台股掃描完成！")

        if all_results:
            final_df = pd.DataFrame(all_results)
            final_df = final_df.sort_values(by="趨勢偏離")
            st.success(f"🎉 找到 {len(final_df)} 檔符合條件標的。")
            st.dataframe(final_df, use_container_width=True)
        else:
            st.warning("☹️ 目前無符合標的，請調低靈敏度後重試。")
