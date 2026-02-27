import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np

# 頁面基礎設定
st.set_page_config(page_title="2026 台股趨勢專業掃描器", layout="wide")

@st.cache_data(ttl=86400)
def get_all_stocks():
    """取得股票清單：優先從穩定來源讀取"""
    try:
        url = "https://raw.githubusercontent.com"
        df = pd.read_csv(url)
        stocks = []
        for _, row in df.iterrows():
            code = str(row['code'])
            name = str(row['name'])
            if len(code) == 4:
                suffix = ".TW" if row['market'] == 'sii' else ".TWO"
                stocks.append({"label": name, "code": code, "symbol": f"{code}{suffix}"})
        return stocks
    except:
        # 權值股備援清單
        data = {"2330":"台積電", "2317":"鴻海", "2454":"聯發科", "2308":"台達電", "2382":"廣達", "2881":"富邦金", "2882":"國泰金", "2891":"中信金"}
        return [{"label": name, "code": code, "symbol": f"{code}.TW"} for code, name in data.items()]

def analyze_batch(df_all, selected_stocks, order):
    """批次分析邏輯：精準處理 MultiIndex 並計算建議價位"""
    results = []
    
    # 檢查下載的資料結構
    if df_all.empty or 'Close' not in df_all:
        return results

    for s in selected_stocks:
        symbol = s['symbol']
        try:
            # 確保從 MultiIndex 中正確提取該股的收盤價
            if symbol not in df_all['Close'].columns:
                continue
                
            series = df_all['Close'][symbol].dropna()
            if len(series) < 40:
                continue
            
            prices = series.values
            # 尋找局部低點
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            
            if len(low_idx) < 2:
                continue
            
            last_low = float(prices[low_idx[-1]])
            prev_low = float(prices[low_idx[-2]])
            curr_price = float(prices[-1])
            
            # 計算 20MA
            ma20 = float(series.rolling(20).mean().iloc[-1])
            
            # 核心邏輯：底底高 + 股價站上 20MA
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
        except Exception:
            continue
            
    return results

# --- UI 介面 ---
st.title("⚡ TW 2026 台股趨勢自動掃描系統 (專業版)")
st.markdown("採用 **yfinance 批次模式**，自動計算買進/賣出建議價位。")

with st.sidebar:
    st.header("設定參數")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 10, help="Order 越大，篩選出的轉折點越顯著。若找不到標的，請調低此數值。")
    limit = st.number_input("掃描數量 (建議 50-200)", 10, 1000, 50)
    start_btn = st.button("🚀 開始高速掃描")

if start_btn:
    with st.status("🚀 執行高速掃描中...", expanded=True) as status:
        st.write("📋 正在初始化股票清單...")
        all_stocks = get_all_stocks()
        selected_stocks = all_stocks[:int(limit)]
        symbols = [s['symbol'] for s in selected_stocks]
        
        st.write(f"📥 正在下載 {len(symbols)} 檔資料並分析趨勢...")
        # 下載資料
        df_all = yf.download(symbols, period="6mo", progress=False, group_by='column')
        
        # 執行批次分析
        final_results = analyze_batch(df_all, selected_stocks, sens)
        
        status.update(label="✅ 掃描任務完成！", state="complete", expanded=False)

    if final_results:
        final_df = pd.DataFrame(final_results)
        # 依價位由高到低排序
        final_df = final_df.sort_values(by="現價", ascending=False)
        
        st.success(f"🎉 在 {len(selected_stocks)} 檔中找到 {len(final_df)} 檔符合條件標的！")
        
        # 欄位重新排序與抬頭顯示
        display_cols = ['股票名稱', '代號', '現價', '建議買進', '建議賣出', '支撐價位', '幅度']
        st.dataframe(
            final_df[display_cols], 
            use_container_width=True,
            column_config={
                "現價": st.column_config.NumberColumn(format="%.2f"),
                "建議買進": st.column_config.NumberColumn(format="%.2f", help="參考支撐價位上浮 1%"),
                "建議賣出": st.column_config.NumberColumn(format="%.2f", help="預估短線獲利 10%"),
                "支撐價位": st.column_config.NumberColumn(format="%.2f")
            }
        )
    else:
        st.warning("☹️ 未找到符合條件標的，建議**增加掃描數量**或將**靈敏度 (Order) 調低**（例如 5-8）。")
