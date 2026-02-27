import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import time

# 頁面基礎設定
st.set_page_config(page_title="2026 全台股趨勢終極掃描器", layout="wide")

@st.cache_data(ttl=86400)
def get_full_taiwan_stock_list():
    """取得完整的全台股清單 (上市+上櫃)"""
    try:
        # 使用 GitHub 穩定來源，抓取所有台股編號
        url = "https://raw.githubusercontent.com"
        df = pd.read_csv(url)
        stocks = []
        for _, row in df.iterrows():
            code = str(row['code'])
            name = str(row['name'])
            # 篩選 4 碼普通股
            if len(code) == 4:
                suffix = ".TW" if row['market'] == 'sii' else ".TWO"
                stocks.append({"label": name, "code": code, "symbol": f"{code}{suffix}"})
        return stocks
    except Exception as e:
        st.error(f"清單獲取失敗: {e}")
        return []

def analyze_chunk(df_chunk, selected_stocks_chunk, order):
    """分析一組批次資料"""
    results = []
    if df_chunk.empty or 'Close' not in df_chunk:
        return results

    for s in selected_stocks_chunk:
        symbol = s['symbol']
        try:
            if symbol not in df_chunk['Close'].columns:
                continue
                
            series = df_chunk['Close'][symbol].dropna()
            if len(series) < 40: continue
            
            prices = series.values
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            
            if len(low_idx) < 2: continue
            
            last_low = float(prices[low_idx[-1]])
            prev_low = float(prices[low_idx[-2]])
            curr_price = float(prices[-1])
            ma20 = float(series.rolling(20).mean().iloc[-1])
            
            # 趨勢邏輯：底底高 + 站上 20MA
            if last_low > prev_low and curr_price > ma20:
                results.append({
                    "股票名稱": s['label'],
                    "代號": s['code'],
                    "現價": round(curr_price, 2),
                    "建議買進": round(last_low * 1.01, 2),
                    "建議賣出": round(curr_price * 1.10, 2),
                    "支撐價位": round(last_low, 2),
                    "幅度": f"{round((curr_price/last_low-1)*100, 1)}%"
                })
        except:
            continue
    return results

# --- UI 介面 ---
st.title("🛡️ TW 2026 全台股趨勢終極掃描系統")
st.markdown("本模式將遍歷**全台上市櫃約 1,800+ 檔個股**，自動篩選底底高且站上 20MA 的標的。")

with st.sidebar:
    st.header("掃描設定")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 8, help="建議設為 5-10 以獲得較多標的")
    st.info("💡 全台股掃描約需 2-5 分鐘，請保持網頁開啟。")
    start_btn = st.button("🔥 啟動全台股深度掃描")

if start_btn:
    all_stocks = get_full_taiwan_stock_list()
    
    if not all_stocks:
        st.error("無法載入股票清單。")
    else:
        total_count = len(all_stocks)
        chunk_size = 100 # 每組下載 100 檔，避免被 Yahoo 封鎖
        all_results = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 開始分批掃描
        with st.spinner("深度掃描進行中..."):
            for i in range(0, total_count, chunk_size):
                chunk = all_stocks[i : i + chunk_size]
                symbols = [s['symbol'] for s in chunk]
                
                status_text.text(f"正在掃描區段: {i} ~ {min(i+chunk_size, total_count)} (總計 {total_count} 檔)")
                
                # 批次下載
                try:
                    df_batch = yf.download(symbols, period="6mo", progress=False, group_by='column')
                    # 執行分析
                    chunk_results = analyze_chunk(df_batch, chunk, sens)
                    all_results.extend(chunk_results)
                except Exception as e:
                    st.warning(f"區段 {i} 抓取異常，已跳過。")
                
                # 更新進度條
                progress_bar.progress(min((i + chunk_size) / total_count, 1.0))
                # 稍微延遲避免請求過快
                time.sleep(0.5)

        status_text.text("✅ 全台股深度掃描完成！")

        if all_results:
            final_df = pd.DataFrame(all_results)
            # 依價位排序
            final_df = final_df.sort_values(by="現價", ascending=False)
            
            st.success(f"🎉 掃描完畢！在全台股中找到 {len(final_df)} 檔符合條件標的。")
            
            # 顯示表格
            display_cols = ['股票名稱', '代號', '現價', '建議買進', '建議賣出', '支撐價位', '幅度']
            st.dataframe(
                final_df[display_cols], 
                use_container_width=True,
                column_config={
                    "現價": st.column_config.NumberColumn(format="%.2f"),
                    "建議買進": st.column_config.NumberColumn(format="%.2f"),
                    "建議賣出": st.column_config.NumberColumn(format="%.2f"),
                    "支撐價位": st.column_config.NumberColumn(format="%.2f")
                }
            )
        else:
            st.warning("☹️ 掃描全台股後未發現符合條件標的，請嘗試調低「靈敏度 (Order)」。")

