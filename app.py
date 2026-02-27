import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np

# 頁面基礎設定
st.set_page_config(page_title="2026 台股趨勢加速篩選器", layout="wide")

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
                stocks.append({"label": f"{name}", "code": code, "symbol": f"{code}{suffix}"})
        return stocks
    except:
        # 備援清單：主要權值股
        data = {"2330":"台積電", "2317":"鴻海", "2454":"聯發科", "2308":"台達電", "2382":"廣達"}
        return [{"label": name, "code": code, "symbol": f"{code}.TW"} for code, name in data.items()]

def analyze_batch(df_all, symbols, order):
    """批次分析邏輯：處理下載後的資料並計算建議價位"""
    results = []
    for symbol in symbols:
        try:
            if symbol not in df_all['Close']: continue
            df = df_all['Close'][symbol].dropna()
            if len(df) < 40: continue
            
            prices = df.values.flatten()
            low_idx = argrelextrema(prices, np.less, order=order)
            if len(low_idx) < 2: continue
            
            last_low = float(prices[low_idx[-1]])
            prev_low = float(prices[low_idx[-2]])
            curr_price = float(prices[-1])
            ma20 = float(df.rolling(20).mean().iloc[-1])
            
            # 趨勢篩選：底底高 + 站上 20MA
            if last_low > prev_low and curr_price > ma20:
                results.append({
                    "代號": symbol.split('.')[0],
                    "現價": round(curr_price, 2),
                    "支撐價位": round(last_low, 2),
                    "建議買進": round(last_low * 1.01, 2), # 支撐位上浮 1%
                    "建議賣出": round(curr_price * 1.10, 2), # 現價獲利 10% 預估
                    "漲幅空間": f"{round((curr_price/last_low-1)*100, 1)}%"
                })
        except:
            continue
    return results

# --- UI 介面 ---
st.title("⚡ TW 2026 台股趨勢自動掃描系統 (專業版)")
st.markdown("採用 **yfinance 批次模式**，自動計算**買進/賣出建議價位**。")

with st.sidebar:
    st.header("設定參數")
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 10)
    limit = st.number_input("掃描數量 (建議 50-200)", 10, 1000, 100)
    start_btn = st.button("🚀 開始高速掃描")

if start_btn:
    with st.status("🚀 執行趨勢掃描中...", expanded=True) as status:
        all_stocks = get_all_stocks()
        selected_stocks = all_stocks[:int(limit)]
        symbols = [s['symbol'] for s in selected_stocks]
        
        st.write(f"📥 正在批次下載 {len(symbols)} 檔資料並計算建議價位...")
        df_all = yf.download(symbols, period="6mo", progress=False, group_by='column')
        
        analysis_results = analyze_batch(df_all, symbols, sens)
        
        final_results = []
        name_map = {s['code']: s['label'] for s in selected_stocks}
        for res in analysis_results:
            res['股票名稱'] = name_map.get(res['代號'], "未知")
            final_results.append(res)
            
        status.update(label="✅ 掃描任務完成！", state="complete", expanded=False)

    if final_results:
        final_df = pd.DataFrame(final_results)
        
        # 1. 依據現價由高到低排序
        final_df = final_df.sort_values(by="現價", ascending=False)
        
        # 2. 重新排列顯示欄位，符合您的抬頭需求
        display_columns = ['股票名稱', '代號', '現價', '建議買進', '建議賣出', '支撐價位', '漲幅空間']
        final_df = final_df[display_columns]
        
        st.success(f"🎉 找到 {len(final_df)} 檔符合條件標的！(已依現價高低排序)")
        
        # 3. 顯示表格 (可下載 CSV)
        st.dataframe(
            final_df, 
            use_container_width=True,
            column_config={
                "現價": st.column_config.NumberColumn(format="%.2f"),
                "建議買進": st.column_config.NumberColumn(help="支撐位附近進場較安全", format="%.2f"),
                "建議賣出": st.column_config.NumberColumn(help="預設短線目標獲利 10%", format="%.2f"),
                "支撐價位": st.column_config.NumberColumn(format="%.2f")
            }
        )
    else:
        st.warning("☹️ 未找到符合條件標的，建議增加掃描數量或調整靈敏度。")
