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
    """讀取台股清單 (確保格式為 .TW)"""
    cache_file = "taiwan_stock_list.csv"
    fallback = {"2330.TW": "台積電", "2317.TW": "鴻海"}
    
    if not os.path.exists(cache_file): return fallback
    try:
        # 嘗試不同編碼讀取 CSV
        for enc in ['utf-8-sig', 'big5', 'gbk']:
            try:
                df = pd.read_csv(cache_file, dtype=str, encoding=enc)
                break
            except: continue
            
        # 自動識別「代號」與「名稱」欄位
        code_col = next((c for c in df.columns if any(k in c for k in ['代號', 'code', 'Symbol'])), df.columns[0])
        name_col = next((c for c in df.columns if any(k in c for k in ['名稱', 'name', 'Label'])), df.columns[1])
        
        # 清洗代號：只留四位數字並補上 .TW
        df['clean_code'] = df[code_col].str.extract(r'(\d{4})')
        df = df.dropna(subset=['clean_code'])
        return {f"{row['clean_code']}.TW": str(row[name_col]).strip() for _, row in df.iterrows()}
    except: return fallback

# --- 2. 強化版波段分析引擎 ---
def analyze_sop_strategy(df, vol_multiplier):
    try:
        # 關鍵修正：確保資料不含空值且長度足夠
        df = df.dropna(subset=['Close', 'Volume'])
        if len(df) < 40: return None
            
        # 計算指標
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['VMA20'] = df['Volume'].rolling(window=20).mean()
        
        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 【條件 1】：基礎趨勢 (收盤 > 20MA) - 這是最重要的放寬
        if curr['Close'] <= curr['MA20']: return None

        # 【條件 2】：帶量突破或回測
        is_breakout = (curr['Close'] > prev['High']) and (curr['Volume'] > curr['VMA20'] * vol_multiplier)
        is_support = (curr['Low'] <= curr['MA20'] * 1.05) and (curr['Close'] >= curr['MA20'] * 0.95)

        if is_breakout or is_support:
            return {
                "Priority": 1 if is_breakout else 2,
                "型態": "🚀 帶量突破" if is_breakout else "📉 靠近支撐",
                "現價": round(curr['Close'], 2),
                "MA20": round(curr['MA20'], 2),
                "MACD": "🔴 紅柱" if hist.iloc[-1] > 0 else "⚪ 綠柱",
                "量能倍數": f"{round(curr['Volume']/curr['VMA20'], 1)}x",
                "防守": round(curr['MA20'] * 0.98, 2)
            }
    except: return None

# --- 3. UI 介面 ---
st.title("⚡ 2026 波段精確掃描器")
st.caption("📱 手機優化版 | 已自動處理代號格式")

stock_dict = get_stock_list()
symbols = list(stock_dict.keys())

with st.expander("⚙️ 掃描門檻設定", expanded=True):
    vol_target = st.slider("🔥 成交量倍數 (1.0x 為放寬版)", 0.5, 3.0, 1.0, 0.1)
    st.info(f"待掃描總數：`{len(symbols)}` 檔")
    start_btn = st.button("🚀 開始掃描", use_container_width=True)

if start_btn:
    all_results = []
    progress_bar = st.progress(0)
    percent_text = st.empty()
    
    start_time = time.time()
    
    with st.spinner("正在抓取大盤數據..."):
        # 關鍵修正： group_by='ticker' 確保多檔股票下載時格式不會跑掉
        data = yf.download(symbols, period="3mo", group_by='ticker', threads=False, progress=False)
        
        total = len(symbols)
        for idx, (sym, name) in enumerate(stock_dict.items()):
            try:
                # 處理 yfinance 回傳的 Data 結構
                if total > 1:
                    if sym not in data.columns.levels[0]: continue
                    stock_df = data[sym].copy()
                else:
                    stock_df = data.copy()
                
                res = analyze_sop_strategy(stock_df, vol_target)
                if res:
                    res["股票"] = f"{sym.split('.')[0]} {name}"
                    all_results.append(res)
            except: continue
            
            # 更新進度與百分比
            if (idx + 1) % 10 == 0 or (idx + 1) == total:
                progress = (idx + 1) / total
                progress_bar.progress(progress)
                percent_text.markdown(f"**目前進度：{int(progress * 100)}%** (`{idx+1}/{total}`)")

    st.success(f"✅ 掃描完成！總耗時: {time.time() - start_time:.1f} 秒")

    # --- 4. 結果呈現 (手機卡片版) ---
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
                m3.metric("量能", row['量能倍數'])
                st.markdown(f"指標：`{row['MACD']}` | 防守點：`{row['防守']}`")
    else:
        st.warning("目前市面上無符合標的。請檢查：\n1. 滑桿是否調太高？\n2. `taiwan_stock_list.csv` 的代號是否為純數字？")

st.divider()
st.caption("⚠ 本系統僅供參考。若持續抓不到數據，請確認您的 `taiwan_stock_list.csv` 格式是否正確。")
