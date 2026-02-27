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
    # 預設測試標的 (增加更多標的以供測試)
    fallback = {"2867.TW": "三商壽", "2017.TW": "官田鋼", "1714.TW": "和桐", 
                "8443.TW": "阿瘦", "1517.TW": "利奇", "2330.TW": "台積電", 
                "2317.TW": "鴻海", "2603.TW": "長榮", "2454.TW": "聯發科"}
    
    if not os.path.exists(cache_file): return fallback
    try:
        df = pd.read_csv(cache_file, dtype=str, encoding='utf-8-sig')
        df['clean_code'] = df.iloc[:, 0].str.extract(r'(\d{4})')
        return {f"{row['clean_code']}.TW": str(df.iloc[i, 1]).strip() for i, row in df.iterrows()}
    except: return fallback

# --- 2. 波段分析引擎 (支援動態量能倍數) ---
def analyze_sop_strategy(df, symbol, name, vol_multiplier):
    try:
        if df is None or len(df) < 60: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            
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
        
        # 【條件 1】：基礎趨勢 (收盤 > 20MA)
        if not (curr['Close'] > curr['MA20']): return None

        # 【條件 2】：帶量突破 (使用滑桿傳入的 vol_multiplier)
        is_breakout = (curr['Close'] > prev['High']) and (curr['Volume'] > curr['VMA20'] * vol_multiplier)
        
        # 【條件 3】：回測支撐 (放寬至 5% 區間)
        is_support = (curr['Low'] <= curr['MA20'] * 1.05) and (curr['Close'] >= curr['MA20'] * 0.95)

        if is_breakout or is_support:
            return {
                "Priority": 1 if is_breakout else 2,
                "股票": f"{symbol.split('.')[0]} {name}",
                "型態": "🚀 帶量突破" if is_breakout else "📉 靠近支撐",
                "現價": round(curr['Close'], 2),
                "MA20": round(curr['MA20'], 2),
                "MACD": "🔴 紅柱" if hist.iloc[-1] > 0 else "⚪ 綠柱",
                "成交量": f"🔥 {round(curr['Volume']/curr['VMA20'], 1)}倍",
                "防守點": round(curr['MA20'] * 0.97, 2)
            }
    except: return None

# --- 3. UI 介面 ---
st.title("⚡ 2026 波段精確掃描器")
st.caption("📱 手機優化介面 | 支援動態門檻調整")

stock_dict = get_stock_list()
symbols = list(stock_dict.keys())

with st.expander("⚙️ 掃描參數與門檻設定", expanded=True):
    # 新增量能滑桿
    vol_target = st.slider("🔥 成交量倍數門檻 (相對於20MA量)", 1.0, 3.0, 1.2, 0.1)
    
    st.markdown(f"**目前條件**：收盤 > 20MA + 量能 > `{vol_target}` 倍")
    st.markdown(f"**待掃描總數**：`{len(symbols)}` 檔")
    start_btn = st.button("🚀 開始掃描分析", use_container_width=True)

if start_btn:
    all_results = []
    # 建立進度條與百分比佔位符
    progress_bar = st.progress(0)
    percent_text = st.empty()
    
    start_time = time.time()
    
    with st.spinner("正在分析市場大數據..."):
        # 批量抓取 (yf.download 會自動處理多檔股票)
        raw_data = yf.download(symbols, period="6mo", threads=False, progress=False)
        
        total = len(symbols)
        for idx, (sym, name) in enumerate(stock_dict.items()):
            try:
                stock_df = raw_data[sym] if total > 1 else raw_data
                if stock_df.empty: continue
                
                # 傳入滑桿設定的量能倍數
                res = analyze_sop_strategy(stock_df, sym, name, vol_target)
                if res: all_results.append(res)
            except: continue
            
            # 更新進度條與百分比
            current_progress = (idx + 1) / total
            progress_bar.progress(current_progress)
            percent_text.markdown(f"**目前進度：{int(current_progress * 100)}%** (`{idx+1}/{total}`)")

    st.success(f"✅ 掃描完成！總耗時: {time.time() - start_time:.1f} 秒")

    # --- 4. 結果呈現 ---
    if all_results:
        df_res = pd.DataFrame(all_results).sort_values(by=["Priority", "現價"], ascending=[True, False])
        st.subheader(f"🎯 發現 {len(all_results)} 檔進場訊號")
        
        for _, row in df_res.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([1.5, 1])
                c1.subheader(row['股票'])
                c2.markdown(f"### {row['型態']}")
                
                m1, m2, m3 = st.columns(3)
                m1.metric("現價", f"{row['現價']}")
                m2.metric("20MA", f"{row['MA20']}")
                m3.metric("防守位", f"{row['防守點']}", delta_color="inverse")
                
                st.markdown(f"指標：`{row['MACD']}` | 量能：`{row['成交量']}`")
    else:
        st.info(f"在量能 {vol_target} 倍的門檻下，暫無符合標的。請嘗試調低滑桿數值。")

st.divider()
st.caption("⚠️ 本系統僅供參考。量能倍數越高代表動能越強，但數量會越少。")
