import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import time
import ssl
import requests
from io import StringIO

# --- 核心修復：忽略 SSL 憑證並停用警告 ---
ssl._create_default_https_context = ssl._create_unverified_context
requests.packages.urllib3.disable_warnings()

# 頁面基礎設定
st.set_page_config(page_title="2026 全台股趨勢終極掃描器", layout="wide")

@st.cache_data(ttl=86400)
def get_full_taiwan_stock_list():
    """模擬瀏覽器行為，從證交所獲取清單並修正 No tables found 錯誤"""
    stocks = []
    urls = [
        ("https://isin.twse.com.tw", ".TW"),  # 上市
        ("https://isin.twse.com.tw", ".TWO") # 上櫃
    ]
    
    # 模擬 Chrome 瀏覽器 Header，避免被伺服器拒絕
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    }

    try:
        for url, suffix in urls:
            # 關鍵修正：先用 requests 抓取，指定編碼後再餵給 pandas
            response = requests.get(url, headers=headers, verify=False, timeout=15)
            response.encoding = 'big5' # 證交所使用 big5 編碼
            
            # 使用 StringIO 封裝，避免 pandas 直接讀取 URL 失敗
            html_data = StringIO(response.text)
            df_list = pd.read_html(html_data)
            
            if not df_list: continue
            df = df_list[0]
            
            # 整理資料：設定欄位名
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            for item in df['有價證券代號及名稱']:
                if pd.isna(item): continue
                parts = item.replace('　', ' ').split(' ')
                if len(parts) >= 2:
                    code = parts[0]
                    name = parts[1]
                    # 只抓取 4 碼純數字普通股
                    if len(code) == 4 and code.isdigit():
                        stocks.append({"label": name, "code": code, "symbol": f"{code}{suffix}"})
        return stocks
    except Exception as e:
        st.error(f"清單獲取失敗: {e}")
        return []

def analyze_chunk(df_batch, selected_stocks_chunk, order):
    """分析邏輯：篩選底底高且站上 20MA 的標的"""
    results = []
    if df_batch is None or df_batch.empty:
        return results

    for s in selected_stocks_chunk:
        symbol = s['symbol']
        try:
            # 檢查 yfinance 多重索引欄位
            if symbol not in df_batch['Close'].columns:
                continue
            series = df_batch['Close'][symbol].dropna()
            if len(series) < 40: continue
            
            prices = series.values
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            if len(low_idx) < 2: continue
            
            last_low, prev_low, curr_price = float(prices[low_idx[-1]]), float(prices[low_idx[-2]]), float(prices[-1])
            ma20 = float(series.rolling(20).mean().iloc[-1])
            
            if last_low > prev_low and curr_price > ma20:
                results.append({
                    "股票名稱": s['label'], "代號": s['code'], "現價": round(curr_price, 2),
                    "支撐價": round(last_low, 2), "建議買點": round(last_low * 1.01, 2),
                    "幅度": f"{round((curr_price/last_low-1)*100, 1)}%"
                })
        except: continue
    return results

# --- UI 介面 ---
st.title("🛡️ TW 2026 全台股趨勢終極掃描系統")
st.markdown("自動遍歷全台上市櫃約 **1,800+ 檔個股**，篩選**底底高**且**站上 20MA** 的標的。")

with st.sidebar:
    st.header("掃描設定")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 8, help="建議 5-10")
    st.info("💡 全台股掃描約需 3-5 分鐘，請保持網頁開啟。")
    start_btn = st.button("🔥 啟動全台股深度掃描")

if start_btn:
    all_stocks = get_full_taiwan_stock_list()
    if not all_stocks:
        st.error("無法載入股票清單，可能被伺服器阻擋，請稍後再試。")
    else:
        total_count = len(all_stocks)
        chunk_size = 50 
        all_results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with st.spinner("掃描進行中..."):
            for i in range(0, total_count, chunk_size):
                chunk = all_stocks[i : i + chunk_size]
                symbols = [s['symbol'] for s in chunk]
                status_text.text(f"掃描進度: {i} / {total_count}")
                try:
                    # 使用多執行緒 threads=True 加速
                    df_batch = yf.download(symbols, period="6mo", progress=False, group_by='column', threads=True)
                    all_results.extend(analyze_chunk(df_batch, chunk, sens))
                except: pass
                progress_bar.progress(min((i + chunk_size) / total_count, 1.0))
                time.sleep(0.3)

        status_text.text("✅ 全台股掃描完成！")
        if all_results:
            st.success(f"🎉 找到 {len(all_results)} 檔符合條件標的。")
            st.dataframe(pd.DataFrame(all_results), use_container_width=True)
        else:
            st.warning("☹️ 未發現符合標的。")
