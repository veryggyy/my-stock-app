import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
import time

# --- 1. 頁面與資料設定 (優化手機窄螢幕配置) ---
st.set_page_config(page_title="2026 台股波段掃描", layout="centered") 

@st.cache_data(ttl=3600)
def get_stock_list():
    """讀取台股清單"""
    cache_file = "taiwan_stock_list.csv"
    # 預設範例標的
    fallback = {"2330.TW": "台積電", "2317.TW": "鴻海", "2867.TW": "三商壽", "2017.TW": "官田鋼", "1714.TW": "和桐"}
    
    if not os.path.exists(cache_file): return fallback
    try:
        df = pd.read_csv(cache_file, dtype=str, encoding='utf-8-sig')
        df['clean_code'] = df.iloc[:, 0].str.extract(r'(\d{4})')
        return {f"{row['clean_code']}.TW": str(df.iloc[i, 1]).strip() for i, row in df.iterrows()}
    except: return fallback

# --- 2. 策略引擎 ---
def analyze_sop_strategy(df, symbol, name):
    try:
        if df is None or len(df) < 60: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            
        # 計算指標
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['VMA20'] = df['Volume'].rolling(window=20).mean()
        
        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 篩選核心：多頭排列
        if not (curr['MA20'] > curr['MA60']): return None

        # 訊號 A：帶量突破 (優化排序權重：1)
        is_breakout = (curr['Close'] > prev['High']) and (curr['Volume'] > curr['VMA20'] * 1.5)
        # 訊號 B：回測支撐 (優化排序權重：2)
        is_support = (curr['Low'] <= curr['MA20'] * 1.02) and (curr['Close'] >= curr['MA20'] * 0.98) and (hist.iloc[-1] > 0)

        if is_breakout or is_support:
            return {
                "Sort": 1 if is_breakout else 2,
                "股票": f"{symbol.split('.')[0]} {name}",
                "型態": "🚀 帶量突破" if is_breakout else "📉 回測支撐",
                "現價": round(curr['Close'], 2),
                "MA20": round(curr['MA20'], 2),
                "MACD": "🔴 紅柱續強" if hist.iloc[-1] > hist.iloc[-2] else "⚪ 紅柱轉弱",
                "量能": "🔥 爆量" if curr['Volume'] > curr['VMA20'] * 1.5 else "正常",
                "防守點": round(curr['MA20'] * 0.98, 2),
                "Time": curr.name
            }
    except: return None

# --- 3. UI 介面 ---
st.header("⚡ 2026 波段精確掃描器")
st.caption("📱 已針對行動裝置優化視覺呈現")

stock_dict = get_stock_list()
symbols = list(stock_dict.keys())

# 手機版將側邊欄精簡
with st.expander("⚙️ 掃描參數設定"):
    st.write(f"篩選條件：20MA > 60MA + 帶量/回測")
    st.write(f"待掃描：{len(symbols)} 檔")
    start_btn = st.button("🚀 開始掃描分析", use_container_width=True)

if start_btn:
    all_results = []
    progress_bar = st.progress(0)
    
    start_time = time.time()
    with st.spinner("分析中..."):
        # 抓取數據 (針對手機環境穩定性，不使用 threads)
        raw_data = yf.download(symbols, period="6mo", interval="1d", threads=False, progress=False)
        
        for idx, (sym, name) in enumerate(stock_dict.items()):
            try:
                stock_df = raw_data[sym] if len(symbols) > 1 else raw_data
                res = analyze_sop_strategy(stock_df, sym, name)
                if res: all_results.append(res)
            except: continue
            progress_bar.progress((idx + 1) / len(symbols))

    # --- 4. 結果呈現 (手機優化版) ---
    if all_results:
        # 依型態(Sort)與現價排序
        df_res = pd.DataFrame(all_results).sort_values(by=["Sort", "現價"], ascending=[True, False])
        
        st.success(f"🎯 發現 {len(all_results)} 檔進場訊號")
        
        for _, row in df_res.iterrows():
            with st.container(border=True):
                # 第一排：股票與型態
                col1, col2 = st.columns([2, 1])
                col1.subheader(row['股票'])
                col2.write(f"**{row['型態']}**")
                
                # 第二排：關鍵指標 (卡片式)
                m1, m2, m3 = st.columns(3)
                m1.metric("現價", row['現價'])
                m2.metric("20MA", row['MA20'])
                m3.metric("防守", row['防守點'], delta_color="inverse")
                
                # 第三排：狀態標籤
                st.markdown(f"指標：`{row['MACD']}` | 量能：`{row['量能']}`")
                
                # 下單參考按鈕 (手機好點擊)
                st.button(f"查看 {row['股票']} 詳情", key=row['股票'], use_container_width=True)
    else:
        st.warning("暫無符合訊號之標的。")

st.divider()
st.caption("⚠ 本系統僅供參考。波段操作應注意停損，並搭配籌碼面判斷。")
