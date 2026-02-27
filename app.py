import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
import time

# --- 1. 頁面與資料設定 (優化手機窄螢幕配置) ---
st.set_page_config(page_title="2026 台股波段掃描器", layout="centered")

@st.cache_data(ttl=3600)
def get_stock_list():
    """讀取台股清單 (支援 csv 或預設範例)"""
    cache_file = "taiwan_stock_list.csv"
    # 預設測試標的
    fallback = {"2867.TW": "三商壽", "2017.TW": "官田鋼", "1714.TW": "和桐", 
                "8443.TW": "阿瘦", "1517.TW": "利奇", "2330.TW": "台積電"}
    
    if not os.path.exists(cache_file): return fallback
    try:
        df = pd.read_csv(cache_file, dtype=str, encoding='utf-8-sig')
        df['clean_code'] = df.iloc[:, 0].str.extract(r'(\d{4})')
        return {f"{row['clean_code']}.TW": str(df.iloc[i, 1]).strip() for i, row in df.iterrows()}
    except: return fallback

# --- 2. 波段分析引擎 ---
def analyze_sop_strategy(df, symbol, name):
    try:
        if df is None or len(df) < 60: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            
        # 技術指標計算
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['VMA20'] = df['Volume'].rolling(window=20).mean()
        
        # MACD 計算
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 篩選：20MA > 60MA (趨勢向上)
        if not (curr['MA20'] > curr['MA60']): return None

        # 訊號 A：帶量突破 (權重 1)
        is_breakout = (curr['Close'] > prev['High']) and (curr['Volume'] > curr['VMA20'] * 1.5)
        # 訊號 B：回測支撐 (權重 2)
        is_support = (curr['Low'] <= curr['MA20'] * 1.02) and (curr['Close'] >= curr['MA20'] * 0.98) and (hist.iloc[-1] > 0)

        if is_breakout or is_support:
            return {
                "Priority": 1 if is_breakout else 2,
                "股票": f"{symbol.split('.')[0]} {name}",
                "型態": "🚀 帶量突破" if is_breakout else "📉 回測支撐",
                "現價": round(curr['Close'], 2),
                "MA20": round(curr['MA20'], 2),
                "MACD": "🔴 紅柱續強" if hist.iloc[-1] > hist.iloc[-2] else "⚪ 紅柱轉弱",
                "成交量": "🔥 爆量" if curr['Volume'] > curr['VMA20'] * 1.5 else "正常",
                "防守點": round(curr['MA20'] * 0.98, 2)
            }
    except: return None

# --- 3. UI 介面設計 ---
st.title("⚡ 2026 波段精確掃描器")
st.caption("📱 已針對行動裝置優化視覺呈現")

stock_dict = get_stock_list()
symbols = list(stock_dict.keys())

# 手機版參數摺疊器
with st.expander("⚙️ 掃描參數設定", expanded=True):
    st.markdown(f"**篩選條件**：20MA > 60MA + 帶量/回測")
    st.markdown(f"**待掃描**：`{len(symbols)}` 檔")
    start_btn = st.button("🚀 開始掃描分析", use_container_width=True)

if start_btn:
    all_results = []
    progress_bar = st.progress(0)
    
    start_time = time.time()
    with st.spinner("正在大數據分析中..."):
        # 抓取數據 (關閉多執行緒以確保在行動端 server 的穩定性)
        raw_data = yf.download(symbols, period="6mo", threads=False, progress=False)
        
        for idx, (sym, name) in enumerate(stock_dict.items()):
            try:
                stock_df = raw_data[sym] if len(symbols) > 1 else raw_data
                res = analyze_sop_strategy(stock_df, sym, name)
                if res: all_results.append(res)
            except: continue
            progress_bar.progress((idx + 1) / len(symbols))

    st.success(f"✅ 掃描完成！耗時: {time.time() - start_time:.1f} 秒")

    # --- 4. 結果呈現 (手機優化卡片) ---
    if all_results:
        # 排序：突破型在前，現價由高到低
        df_res = pd.DataFrame(all_results).sort_values(by=["Priority", "現價"], ascending=[True, False])
        
        st.subheader(f"🎯 波段進場訊號 (發現 {len(all_results)} 檔)")
        
        for _, row in df_res.iterrows():
            with st.container(border=True):
                # 標題列
                c1, c2 = st.columns([1.5, 1])
                c1.subheader(row['股票'])
                c2.markdown(f"### {row['型態']}")
                
                # 數據指標列 (手機並排顯示)
                m1, m2, m3 = st.columns(3)
                m1.metric("現價", f"{row['現價']}")
                m2.metric("20MA", f"{row['MA20']}")
                m3.metric("防守位", f"{row['防守點']}", delta_color="inverse")
                
                # 底部標籤
                st.markdown(f"MACD：`{row['MACD']}` | 成交量：`{row['成交量']}`")
    else:
        st.info("暫無符合訊號之標的。")

st.divider()
st.caption("⚠️ 本系統僅供參考。波段操作應注意停損，並搭配籌碼面判斷。")
