import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
import re
import time

# --- 1. 頁面與樣式設定 ---
st.set_page_config(page_title="2026 台股趨勢波段掃描器", layout="wide")

# 加大表格字體與優化空間的 CSS
st.markdown("""
    <style>
    [data-testid="stTable"] { font-size: 18px !important; }
    .stDataFrame td { font-size: 16px !important; }
    .stMetric { background-color: #1e2129; padding: 10px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_stock_list():
    cache_file = "taiwan_stock_list.csv"
    fallback = {"2330.TW": "台積電"}
    if not os.path.exists(cache_file): return fallback
    try:
        for enc in ['utf-8-sig', 'big5', 'gbk']:
            try:
                df = pd.read_csv(cache_file, dtype=str, encoding=enc)
                break
            except: continue
        df.columns = [c.strip() for c in df.columns]
        code_col = next((c for c in df.columns if any(k in c for k in ['代號', 'code'])), df.columns[0])
        name_col = next((c for c in df.columns if any(k in c for k in ['名稱', 'label'])), df.columns[min(1, len(df.columns)-1)])
        df['clean_code'] = df[code_col].str.extract(r'(\d{4})')
        df = df.dropna(subset=['clean_code'])
        return {f"{row['clean_code']}.TW": str(row[name_col]).strip() for _, row in df.iterrows()}
    except: return fallback

# --- 2. 核心技術分析 (含排序權重) ---
def analyze_trend_strategy(data, symbol, name):
    try:
        if data is None or len(data) < 70: return None
        df = data.copy()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['VMA20'] = df['Volume'].rolling(window=20).mean()
        
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_hist = (ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()

        curr, prev = df.iloc[-1], df.iloc[-2]
        if not (curr['MA20'] > curr['MA60']): return None

        is_breakout = (curr['Close'] > prev['High']) and (curr['Volume'] > curr['VMA20'] * 1.5)
        is_support = (curr['Low'] <= curr['MA20'] * 1.02) and (curr['Close'] >= curr['MA20'] * 0.99) and (macd_hist.iloc[-1] > 0)

        if is_breakout or is_support:
            # 優先級計算：帶量突破(2分) + 紅柱(1分)
            priority = (2 if is_breakout else 1) + (1 if macd_hist.iloc[-1] > 0 else 0)
            clean_name = re.split(r'[\s0-9]', name)[0]
            
            return {
                "優先級": priority,
                "代號": symbol.split('.')[0],
                "股票名稱": clean_name,
                "現價": round(curr['Close'], 2),
                "買進參考": round(curr['MA20'], 2),
                "目標價": round(curr['Close'] * 1.15, 2),
                "防守位": round(curr['MA20'] * 0.97, 2),
                "型態": "🚀 帶量突破" if is_breakout else "📉 回測支撐",
                "MACD": "🔴 紅柱" if macd_hist.iloc[-1] > 0 else "🟢 綠柱",
                "成交量": "🔥 爆量" if curr['Volume'] > curr['VMA20'] * 1.5 else "正常"
            }
    except: return None

# --- 3. UI 介面 ---
st.title("⚡ TW 2026 極速波段掃描器")

stock_dict = get_stock_list()
symbols = list(stock_dict.keys())

with st.sidebar:
    st.header("⚙️ 策略參數")
    st.info(f"📊 待掃描: {len(symbols)} 檔")
    start_btn = st.button("🚀 啟動完整掃描")

if start_btn:
    all_results = []
    # 建立進場資訊區
    progress_info = st.empty()
    progress_bar = st.progress(0)
    
    start_time = time.time()
    
    try:
        # 下載數據
        raw_data = yf.download(symbols, period="8mo", group_by='ticker', threads=False, progress=False)
        
        for idx, (sym, name) in enumerate(stock_dict.items()):
            # 計算進度與預估時間
            elapsed_time = time.time() - start_time
            processed_count = idx + 1
            avg_time_per_stock = elapsed_time / processed_count
            remaining_stocks = len(symbols) - processed_count
            est_remaining_time = int(avg_time_per_stock * remaining_stocks)
            
            percent = int((processed_count / len(symbols)) * 100)
            progress_info.markdown(f"**🔍 掃描中:** `{percent}%` | **預估剩餘時間:** `{est_remaining_time} 秒` | **正在處理:** `{sym}`")
            progress_bar.progress(processed_count / len(symbols))
            
            try:
                stock_df = raw_data[sym] if len(symbols) > 1 else raw_data
                if stock_df.empty or len(stock_df) < 60: continue
                res = analyze_trend_strategy(stock_df, sym, name)
                if res: all_results.append(res)
            except: continue

        progress_info.success(f"✅ 掃描完成！耗時: {int(time.time() - start_time)} 秒")

    except Exception as e:
        st.error(f"掃描中斷: {e}")

    if all_results:
        # 排序：優先級由高到低，現價由低到高
        df_res = pd.DataFrame(all_results).sort_values(by=["優先級", "現價"], ascending=[False, True])
        
        st.subheader(f"💡 發現 {len(all_results)} 檔優選標的 (由強至弱排序)")
        
        # 使用 column_config 縮小右側欄位面積，增加可視字體
        st.dataframe(
            df_res.drop(columns=['優先級']), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "代號": st.column_config.TextColumn("代號", width="small"),
                "股票名稱": st.column_config.TextColumn("股票名稱", width="medium"),
                "型態": st.column_config.TextColumn("型態", width="small"),
                "MACD": st.column_config.TextColumn("MACD", width="small"),
                "成交量": st.column_config.TextColumn("成交量", width="small"),
            }
        )
    else:
        st.warning("目前市況查無符合條件標的。")

st.markdown("---")
st.caption("2026 穩定版 | 優先級邏輯：帶量突破 > 回測支撐 | 字體已優化")
