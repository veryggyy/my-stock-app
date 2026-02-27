import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import time
import ssl
import requests
from io import StringIO

# --- 核心修復：強制忽略 SSL 並停用連線警告 ---
ssl._create_default_https_context = ssl._create_unverified_context
requests.packages.urllib3.disable_warnings()

# 頁面基礎設定
st.set_page_config(page_title="2026 全台股趨勢終極掃描器", layout="wide")

@st.cache_data(ttl=86400)
def get_full_taiwan_stock_list():
    """模擬真實瀏覽器行為，從證交所獲取清單並修正 No tables found 錯誤"""
    stocks = []
    # 模擬 Chrome 瀏覽器的標頭 (Header)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    }
    urls = [
        ("https://isin.twse.com.tw", ".TW"),  # 上市
        ("https://isin.twse.com.tw", ".TWO") # 上櫃
    ]
    
    try:
        for url, suffix in urls:
            # 關鍵修正：先用 requests 抓取網頁原始碼
            response = requests.get(url, headers=headers, verify=False, timeout=20)
            response.encoding = 'big5' # 證交所使用 Big5 編碼
            
            # 使用 StringIO 封裝，避免 pandas 直接讀取 URL 被阻擋
            df_list = pd.read_html(StringIO(response.text))
            
            if not df_list: continue
            df = df_list[0]
            
            # 整理資料表格
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            for item in df['有價證券代號及名稱']:
                if pd.isna(item): continue
                # 處理「代號 名称」格式，例如 "2330　台積電"
                parts = item.replace('　', ' ').split(' ')
                if len(parts) >= 2:
                    code = parts[0]
                    name = parts[1]
                    # 只抓取 4 碼純數字普通股 (過濾權證、ETF)
                    if len(code) == 4 and code.isdigit():
                        stocks.append({"label": name, "code": code, "symbol": f"{code}{suffix}"})
        return stocks
    except Exception as e:
        st.error(f"清單獲取失敗: {e}")
        return []

def analyze_chunk(df_batch, selected_stocks_chunk, order):
    """分析核心邏輯：篩選底底高且站上 20MA 的標的"""
    results = []
    if df_batch is None or df_batch.empty:
        return results

    for s in selected_stocks_chunk:
        symbol = s['symbol']
        try:
            # 處理 yfinance 多重索引資料結構
            if symbol not in df_batch['Close'].columns:
                continue
                
            series = df_batch['Close'][symbol].dropna()
            if len(series) < 40: continue
            
            prices = series.values
            # 尋找波段低點 (局部極小值)
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            
            if len(low_idx) < 2: continue
            
            last_low = float(prices[low_idx[-1]])
            prev_low = float(prices[low_idx[-2]])
            curr_price = float(prices[-1])
            ma20 = float(series.rolling(20).mean().iloc[-1])
            
            # 策略：最新低點 > 前一低點 (底底高) 且 現價高於 20MA
            if last_low > prev_low and curr_price > ma20:
                results.append({
                    "股票名稱": s['label'],
                    "代號": s['code'],
                    "現價": round(curr_price, 2),
                    "支撐價位": round(last_low, 2),
                    "建議買點": round(last_low * 1.01, 2),
                    "趨勢偏離": f"{round((curr_price/last_low-1)*100, 1)}%"
                })
        except:
            continue
    return results

# --- UI 介面 ---
st.title("🛡️ TW 2026 全台股趨勢終極掃描系統")
st.markdown("系統將自動分析全台 **1,800+ 檔個股**，尋找具備**趨勢轉強**訊號的標的。")

with st.sidebar:
    st.header("掃描設定")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 8, help="建議設為 8-10，數值越小標的越多")
    st.info("💡 全台股掃描約需 3-5 分鐘，請保持網頁開啟。")
    start_btn = st.button("🔥 啟動全台股深度掃描")

if start_btn:
    all_stocks = get_full_taiwan_stock_list()
    
    if not all_stocks:
        st.error("無法載入股票清單，可能被伺服器暫時阻擋，請 10 分鐘後再試。")
    else:
        total_count = len(all_stocks)
        chunk_size = 50 # 分組下載，避免 API 頻繁連線被鎖
        all_results = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.spinner("正在進行全台股大數據分析..."):
            for i in range(0, total_count, chunk_size):
                chunk = all_stocks[i : i + chunk_size]
                symbols = [s['symbol'] for s in chunk]
                
                status_text.text(f"掃描進度: {i} / {total_count} (正在分析第 {i//chunk_size + 1} 梯次)")
                
                try:
                    # 使用 threads=True 加速下載並減少 API 逾時風險
                    df_batch = yf.download(symbols, period="6mo", progress=False, group_by='column', threads=True)
                    chunk_results = analyze_chunk(df_batch, chunk, sens)
                    all_results.extend(chunk_results)
                except Exception:
                    pass 
                
                # 更新 UI 進度
                progress_bar.progress(min((i + chunk_size) / total_count, 1.0))
                time.sleep(0.3)

        status_text.text("✅ 全台股深度掃描完成！")

        if all_results:
            final_df = pd.DataFrame(all_results)
            final_df = final_df.sort_values(by="趨勢偏離")
            
            st.success(f"🎉 掃描完畢！在全台股中找到 {len(final_df)} 檔符合條件標的。")
            st.dataframe(final_df, use_container_width=True)
        else:
            st.warning("☹️ 目前靈敏度下未發現符合標的，請調低靈敏度後重試。")
