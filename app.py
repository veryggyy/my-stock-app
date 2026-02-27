import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import time
import os

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="2026 台股趨勢回測掃描系統", layout="wide")

@st.cache_data(ttl=3600)
def get_full_taiwan_stock_list():
    """自動辨識上市(.TW)與上櫃(.TWO)並清洗資料"""
    cache_file = "taiwan_stock_list.csv"
    if os.path.exists(cache_file):
        try:
            df = pd.read_csv(cache_file, dtype=str)
            df.columns = [c.strip() for c in df.columns]
            code_col = next((c for c in df.columns if 'code' in c.lower() or '代號' in c), df.columns[0])
            label_col = next((c for c in df.columns if 'label' in c.lower() or '名稱' in c or '股票' in c), df.columns[0])
            market_col = next((c for c in df.columns if '市場' in c or '類別' in c), None)

            stocks = []
            for _, row in df.iterrows():
                code = str(row[code_col]).strip()
                name = str(row[label_col]).strip()
                if "." in code:
                    symbol = code.upper()
                elif market_col and ('櫃' in str(row[market_col]) or 'OTC' in str(row[market_col]).upper()):
                    symbol = f"{code}.TWO"
                else:
                    symbol = f"{code}.TW"
                stocks.append({"label": name, "code": code, "symbol": symbol})
            return stocks
        except: pass
    return [{"label": "台積電", "code": "2330", "symbol": "2330.TW"}]

# --- 2. 核心分析邏輯 (增加欄位強健性) ---
def analyze_with_backtest(df_batch, selected_stocks_chunk, order):
    results = []
    backtest_days = 30 
    
    for s in selected_stocks_chunk:
        symbol = s['symbol']
        try:
            # 強制提取該股票的資料，處理 MultiIndex 或單一 Index
            if isinstance(df_batch.columns, pd.MultiIndex):
                if symbol not in df_batch.columns.get_level_values(0): continue
                data = df_batch[symbol].copy()
            else:
                data = df_batch.copy()
            
            data = data.dropna(subset=['Close'])
            if len(data) < 60: continue
            
            prices = data['Close'].values.astype(float)
            curr_price = float(prices[-1])
            ma20 = data['Close'].rolling(20).mean().iloc[-1]
            
            # 尋找低點
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            if len(low_idx) < 2: continue
            
            last_low, prev_low = prices[low_idx[-1]], prices[low_idx[-2]]
            
            # 判斷條件：底底高 + 現價在月線附近或上方
            if last_low > prev_low and curr_price > (ma20 * 0.97):
                # 簡單模擬回測
                sim_return = "N/A"
                hist_data = data.iloc[:-backtest_days]
                if len(hist_data) > 40:
                    h_prices = hist_data['Close'].values
                    h_low_idx = argrelextrema(h_prices, np.less, order=order)[0]
                    if len(h_low_idx) >= 2:
                        if h_prices[h_low_idx[-1]] > h_prices[h_low_idx[-2]] and h_prices[-1] > (hist_data['Close'].rolling(20).mean().iloc[-1] * 0.97):
                            ret = (curr_price / h_prices[-1] - 1) * 100
                            sim_return = f"{round(ret, 1)}%"

                results.append({
                    "股票名稱": s['label'],
                    "代號": s['code'],
                    "現價": round(curr_price, 2),
                    "支撐價": round(last_low, 2),
                    "風險距離%": round((curr_price/last_low-1)*100, 1),
                    "30日模擬報酬": sim_return,
                    "成交量狀態": "🔥 爆量" if data['Volume'].iloc[-1] > data['Volume'].rolling(20).mean().iloc[-1]*2 else "正常"
                })
        except: continue
    return results

# --- 3. UI 介面 ---
st.title("🛡️ TW 2026 趨勢掃描與回測系統")
all_stocks = get_full_taiwan_stock_list()

with st.sidebar:
    st.header("⚙️ 參數設定")
    sens = st.slider("趨勢靈敏度 (Order)", 3, 20, 5) # 最小值降到 3
    st.info(f"📊 當前清單共: {len(all_stocks)} 檔")
    debug_mode = st.checkbox("開啟詳細除錯日誌")
    start_btn = st.button("🚀 啟動掃描與歷史回測")

if start_btn:
    total_count = len(all_stocks)
    chunk_size = 10 
    all_results = []
    progress_bar = st.progress(0)
    status_msg = st.empty()
    
    with st.spinner("正在執行掃描中..."):
        for i in range(0, total_count, chunk_size):
            chunk = all_stocks[i : i + chunk_size]
            symbols = [s['symbol'] for s in chunk]
            
            try:
                # auto_adjust=True 讓價格標準化，免去 Open/Close 欄位混淆
                df_batch = yf.download(symbols, period="1y", progress=False, group_by='ticker', auto_adjust=True)
                
                if not df_batch.empty:
                    batch_res = analyze_with_backtest(df_batch, chunk, sens)
                    all_results.extend(batch_res)
                    if debug_mode and batch_res:
                        st.write(f"✅ 批次 {i} 發現: {[r['股票名稱'] for r in batch_res]}")
            except Exception as e:
                if debug_mode: st.error(f"❌ 批次 {i} 下載錯誤: {e}")
            
            progress_bar.progress(min((i + chunk_size) / total_count, 1.0))
            time.sleep(0.5)

    if all_results:
        df = pd.DataFrame(all_results)
        st.success(f"發現 {len(df)} 檔符合型態標的")
        st.dataframe(df.sort_values(by="風險距離%"), use_container_width=True)
    else:
        st.warning("查無符合標的。可能是網路受阻，請稍後再試或檢查代號。")

st.markdown("---")
st.caption("資料來源：Yahoo Finance。僅供參考。")
