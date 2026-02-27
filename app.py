import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
import re
import time

# --- 1. 頁面與樣式設定 ---
st.set_page_config(page_title="2026 台股趨勢掃描器 (精簡穩定版)", layout="wide")

# CSS 優化：加大字體、縮小邊距
st.markdown("""
    <style>
    [data-testid="stTable"] { font-size: 18px !important; }
    .stDataFrame td { font-size: 16px !important; }
    .stProgress > div > div > div > div { background-color: #00c853; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_stock_list(limit=200):
    """讀取清單並限制數量為 200 檔以確保速度"""
    cache_file = "taiwan_stock_list.csv"
    stocks = {}
    if os.path.exists(cache_file):
        try:
            for enc in ['utf-8-sig', 'big5', 'gbk']:
                try:
                    df = pd.read_csv(cache_file, dtype=str, encoding=enc)
                    break
                except: continue
            
            df.columns = [c.strip() for c in df.columns]
            code_col = next((c for c in df.columns if any(k in c for k in ['代號', 'code'])), df.columns[0])
            name_col = next((c for c in df.columns if any(k in c for k in ['名稱', 'label'])), df.columns[1])
            
            # 限制前 200 檔
            df = df.head(limit)
            stocks = {f"{str(row[code_col]).strip()}.TW": str(row[name_col]).strip() for _, row in df.iterrows()}
        except: pass
    
    if not stocks: # 備援方案
        stocks = {"2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科"}
    return stocks

def analyze_trend_strategy(data, symbol, name):
    """技術分析邏輯"""
    try:
        if data is None or len(data) < 60: return None
        df = data.copy()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            
        # 計算指標
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        df['VMA20'] = df['Volume'].rolling(20).mean()
        
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_hist = (ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()

        curr, prev = df.iloc[-1], df.iloc[-2]
        
        # 1. 趨勢門檻：20MA > 60MA
        if not (curr['MA20'] > curr['MA60']): return None

        # 2. 進場判定
        is_breakout = (curr['Close'] > prev['High']) and (curr['Volume'] > curr['VMA20'] * 1.5)
        is_support = (curr['Low'] <= curr['MA20'] * 1.02) and (curr['Close'] >= curr['MA20'] * 0.99) and (macd_hist.iloc[-1] > 0)

        if is_breakout or is_support:
            # 優先級：帶量突破(2分) > 回測支撐(1分)；MACD紅柱(+1分)
            priority = (2 if is_breakout else 1) + (1 if macd_hist.iloc[-1] > 0 else 0)
            # 名稱清洗：僅保留中文
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
st.title("⚡ TW 2026 極速趨勢掃描器")
st.subheader("🔍 精簡穩定版 (限定掃描前 200 檔)")

stock_dict = get_stock_list(limit=200)
symbols = list(stock_dict.keys())

with st.sidebar:
    st.header("⚙️ 策略參數")
    st.markdown("**🎯 規則：20MA > 60MA + 型態觸發**")
    st.info(f"📊 待掃描清單: {len(symbols)} 檔")
    start_btn = st.button("🚀 啟動掃描")

if start_btn:
    all_results = []
    prog_info = st.empty()
    prog_bar = st.progress(0)
    start_time = time.time()
    
    # 分批下載以防轉圈圈 (每 50 檔一批)
    batch_size = 50
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        
        # 更新預估時間
        elapsed = time.time() - start_time
        processed = i
        if processed > 0:
            remaining = int((elapsed / processed) * (len(symbols) - processed))
        else:
            remaining = "計算中..."
            
        prog_info.markdown(f"**⏳ 掃描進度:** `{int(i/len(symbols)*100)}%` | **預估剩餘:** `{remaining} 秒`")
        prog_bar.progress(i / len(symbols))

        try:
            # threads=False 解決 Python 3.13 轉圈問題
            raw_data = yf.download(batch, period="8mo", group_by='ticker', threads=False, progress=False)
            
            for sym in batch:
                try:
                    df = raw_data[sym] if len(batch) > 1 else raw_data
                    if df.empty: continue
                    res = analyze_trend_strategy(df, sym, stock_dict[sym])
                    if res: all_results.append(res)
                except: continue
        except: continue

    prog_bar.progress(1.0)
    prog_info.success(f"✅ 掃描完成！耗時: {int(time.time() - start_time)} 秒")

    if all_results:
        # 排序：優先級由高到低，現價由低到高
        df_res = pd.DataFrame(all_results).sort_values(by=["優先級", "現價"], ascending=[False, True])
        
        st.subheader(f"💡 發現 {len(all_results)} 檔優選標的 (由強至弱排序)")
        st.dataframe(
            df_res.drop(columns=['優先級']), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "代號": st.column_config.TextColumn("代號", width="small"),
                "股票名稱": st.column_config.TextColumn("股票名稱", width="medium"),
                "現價": st.column_config.NumberColumn("現價", format="%.2f"),
                "型態": st.column_config.TextColumn("型態", width="small"),
                "MACD": st.column_config.TextColumn("MACD", width="small"),
            }
        )
    else:
        st.warning("查無符合多頭排列與進場條件的股票。")

st.markdown("---")
st.caption("2026 穩定版 | 已優化字體與右側空間 | 限定掃描前 200 檔")
