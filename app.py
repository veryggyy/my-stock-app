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
            # 讀取 CSV
            df = pd.read_csv(cache_file, dtype=str)
            df.columns = [c.strip() for c in df.columns]
            
            # 尋找關鍵欄位
            code_col = next((c for c in df.columns if 'code' in c.lower() or '代號' in c), df.columns[0])
            label_col = next((c for c in df.columns if 'label' in c.lower() or '名稱' in c or '股票' in c), df.columns[0])
            market_col = next((c for c in df.columns if '市場' in c or '類別' in c), None)

            stocks = []
            for _, row in df.iterrows():
                code = str(row[code_col]).strip()
                name = str(row[label_col]).strip()
                
                # 自動後綴判斷：若代號本身已有後綴則不處理，否則根據市場判斷
                if "." in code:
                    symbol = code.upper()
                elif market_col and ('櫃' in str(row[market_col]) or 'OTC' in str(row[market_col]).upper()):
                    symbol = f"{code}.TWO"
                else:
                    symbol = f"{code}.TW"
                
                stocks.append({"label": name, "code": code, "symbol": symbol})
            return stocks
        except Exception as e:
            st.error(f"解析 CSV 失敗: {e}")
            
    # 預設回退方案
    return [{"label": "台積電", "code": "2330", "symbol": "2330.TW"}]

def format_num(val):
    try:
        f_val = float(val)
        return int(f_val) if f_val % 1 == 0 else round(f_val, 2)
    except: return val

# --- 2. 核心分析邏輯 ---
def analyze_with_backtest(df_batch, selected_stocks_chunk, order):
    results = []
    backtest_days = 30 
    
    for s in selected_stocks_chunk:
        symbol = s['symbol']
        try:
            # 兼容 yfinance 多檔與單檔下載的資料結構
            if isinstance(df_batch.columns, pd.MultiIndex):
                if symbol not in df_batch.columns.levels[0]: continue
                data = df_batch[symbol].dropna()
            else:
                data = df_batch.dropna()
                
            if len(data) < 60: continue
            
            prices = data['Close'].values
            curr_price = float(prices[-1])
            ma20 = float(data['Close'].rolling(20).mean().iloc[-1])
            
            # 尋找局部低點
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            if len(low_idx) < 2: continue
            
            last_low, prev_low = float(prices[low_idx[-1]]), float(prices[low_idx[-2]])
            
            # --- 回測邏輯 ---
            sim_return = "N/A"
            hist_data = data.iloc[:-backtest_days]
            if len(hist_data) > 40:
                h_prices = hist_data['Close'].values
                h_low_idx = argrelextrema(h_prices, np.less, order=order)[0]
                if len(h_low_idx) >= 2:
                    # 歷史回測：當時滿足 底底高 且 站上均線
                    if h_prices[h_low_idx[-1]] > h_prices[h_low_idx[-2]] and h_prices[-1] > hist_data['Close'].rolling(20).mean().iloc[-1]:
                        ret = (curr_price / h_prices[-1] - 1) * 100
                        sim_return = f"{round(ret, 1)}%"

            # --- 當前篩選條件 (稍微放寬現價限制) ---
            # 條件：1.底底高 2.現價不低於月線 3% (避免錯過剛站回的標的)
            if last_low > prev_low and curr_price > (ma20 * 0.97):
                results.append({
                    "股票名稱": s['label'],
                    "代號": s['code'],
                    "現價": format_num(curr_price),
                    "支撐價": format_num(last_low),
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
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 10, help="數值越小，篩選出的短線轉折越多")
    st.info(f"📊 當前清單共: {len(all_stocks)} 檔")
    debug_mode = st.checkbox("開啟除錯模式 (顯示抓取狀態)")
    start_btn = st.button("🚀 啟動掃描與歷史回測")

if start_btn:
    total_count = len(all_stocks)
    chunk_size = 15  # 縮小批次以防被 Yahoo 封鎖
    all_results = []
    progress_bar = st.progress(0)
    status_msg = st.empty()
    
    with st.spinner("正在下載並分析數據，請稍候..."):
        for i in range(0, total_count, chunk_size):
            chunk = all_stocks[i : i + chunk_size]
            symbols = [s['symbol'] for s in chunk]
            
            if debug_mode:
                status_msg.text(f"掃描中: {symbols[0]} 等 {len(symbols)} 檔...")
                
            try:
                # 下載數據，設定 auto_adjust 為 True 確保價格連續
                df_batch = yf.download(symbols, period="1y", progress=False, group_by='ticker', auto_adjust=True, threads=True)
                
                if not df_batch.empty:
                    batch_res = analyze_with_backtest(df_batch, chunk, sens)
                    all_results.extend(batch_res)
            except Exception as e:
                if debug_mode: st.warning(f"批次錯誤: {e}")
            
            progress_bar.progress(min((i + chunk_size) / total_count, 1.0))
            time.sleep(0.8) # 適度延遲

    status_msg.empty()
    
    if all_results:
        df = pd.DataFrame(all_results)
        # 計算勝率
        valid_rets = [float(x.replace('%','')) for x in df["30日模擬報酬"] if x != "N/A"]
        
        if valid_rets:
            st.subheader("📈 策略績效驗證 (近 30 日)")
            c1, c2, c3 = st.columns(3)
            c1.metric("模擬標的數", f"{len(valid_rets)} 檔")
            win_rate = len([x for x in valid_rets if x > 0])/len(valid_rets)*100
            c2.metric("平均勝率", f"{round(win_rate, 1)}%")
            avg_ret = sum(valid_rets)/len(valid_rets)
            c3.metric("平均報酬", f"{round(avg_ret, 2)}%")
        
        st.success(f"發現 {len(df)} 檔符合型態標的")
        st.dataframe(df.sort_values(by="風險距離%"), use_container_width=True)
    else:
        st.warning("查無符合標的。建議嘗試將「趨勢靈敏度」調低至 5 或 7。")

st.markdown("---")
st.caption("註：本系統僅供型態教學參考，不構成任何投資建議。資料來源：Yahoo Finance")
