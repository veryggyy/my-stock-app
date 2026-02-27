import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
import time

# --- 1. 頁面與資料設定 ---
st.set_page_config(page_title="2026 台股波段掃描器", layout="centered")

@st.cache_data(ttl=3600)
def get_stock_list():
    """讀取台股清單 (確保代號後綴為 .TW)"""
    cache_file = "taiwan_stock_list.csv"
    fallback = {"2330.TW": "台積電", "2317.TW": "鴻海", "2867.TW": "三商壽", "2017.TW": "官田鋼"}
    
    if not os.path.exists(cache_file): return fallback
    try:
        df = pd.read_csv(cache_file, dtype=str, encoding='utf-8-sig')
        # 自動補足 .TW 後綴並移除空格
        return {f"{str(row.iloc[0]).strip().replace('.TW','')}.TW": str(row.iloc[1]).strip() for _, row in df.iterrows()}
    except: return fallback

# --- 2. 強化版分析引擎 (解決 Multi-Index 問題) ---
def analyze_sop_strategy(df, vol_multiplier):
    try:
        # 移除任何空值
        df = df.dropna(subset=['Close', 'Volume'])
        if len(df) < 60: return None
            
        # 計算指標
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['VMA20'] = df['Volume'].rolling(window=20).mean()
        
        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        hist = (exp1 - exp2) - (exp1 - exp2).ewm(span=9, adjust=False).mean()

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 【條件 1】：收盤價 > 月線 (放寬版核心)
        if curr['Close'] <= curr['MA20']: return None

        # 【條件 2】：量能與突破判斷
        is_breakout = (curr['Close'] > prev['High']) and (curr['Volume'] > curr['VMA20'] * vol_multiplier)
        is_support = (curr['Low'] <= curr['MA20'] * 1.05) and (curr['Close'] >= curr['MA20'] * 0.95)

        if is_breakout or is_support:
            return {
                "Type": 1 if is_breakout else 2,
                "型態": "🚀 帶量突破" if is_breakout else "📉 靠近支撐",
                "現價": round(curr['Close'], 2),
                "MA20": round(curr['MA20'], 2),
                "MACD": "🔴 紅柱" if hist.iloc[-1] > 0 else "⚪ 綠柱",
                "量能倍數": round(curr['Volume'] / curr['VMA20'], 2),
                "防守": round(curr['MA20'] * 0.98, 2)
            }
    except Exception as e: return None
    return None

# --- 3. UI 介面 ---
st.title("⚡ 2026 波段精確掃描器")
st.caption("📱 手機優化介面 | 強化資料解析版")

stock_dict = get_stock_list()
symbols = list(stock_dict.keys())

with st.expander("⚙️ 掃描參數設定", expanded=True):
    vol_target = st.slider("🔥 成交量門檻 (相對於20MA量)", 0.5, 3.0, 1.0, 0.1)
    st.info(f"目前條件：收盤 > 20MA + 量能 > {vol_target} 倍 | 總量：{len(symbols)} 檔")
    start_btn = st.button("🚀 啟動深度分析", use_container_width=True)

if start_btn:
    all_results = []
    progress_bar = st.progress(0)
    percent_text = st.empty()
    
    start_time = time.time()
    
    with st.spinner("正在抓取與解析數據..."):
        # 關鍵修正：確保 yf.download 下載格式正確
        data = yf.download(symbols, period="6mo", group_by='ticker', threads=False, progress=False)
        
        for idx, (sym, name) in enumerate(stock_dict.items()):
            try:
                # 處理 yfinance 可能回傳的多層或單層資料結構
                if len(symbols) > 1:
                    if sym not in data.columns.levels[0]: continue
                    stock_df = data[sym].copy()
                else:
                    stock_df = data.copy()

                res = analyze_sop_strategy(stock_df, vol_target)
                if res:
                    res["股票"] = f"{sym.split('.')[0]} {name}"
                    all_results.append(res)
            except: continue
            
            # 更新進度
            if (idx + 1) % 10 == 0 or (idx + 1) == len(symbols):
                progress = (idx + 1) / len(symbols)
                progress_bar.progress(progress)
                percent_text.markdown(f"進度：**{int(progress*100)}%** ({idx+1}/{len(symbols)})")

    st.success(f"✅ 掃描完成！總耗時: {time.time() - start_time:.1f} 秒")

    if all_results:
        df_res = pd.DataFrame(all_results).sort_values(by=["Type", "現價"], ascending=[True, False])
        st.subheader(f"🎯 發現 {len(all_results)} 檔符合標的")
        for _, row in df_res.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([1.5, 1])
                c1.subheader(row['股票'])
                c2.markdown(f"### {row['型態']}")
                m1, m2, m3 = st.columns(3)
                m1.metric("現價", row['現價'])
                m2.metric("20MA", row['MA20'])
                m3.metric("量能", f"{row['量能倍數']}x")
                st.markdown(f"狀態：`{row['MACD']}` | 防守位：`{row['防守']}`")
    else:
        st.warning("⚠️ 掃描完畢但無符合個股。建議：\n1. 檢查 `taiwan_stock_list.csv` 代號格式（需如 2330）。\n2. 目前可能是非開盤時段，數據尚未更新。")

st.divider()
st.caption("本系統數據由 yfinance 提供。若持續無結果，請確認網路連接或更換 API Key。")
