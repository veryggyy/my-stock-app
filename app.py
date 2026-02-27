import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
import time

# --- 1. 頁面與資料設定 ---
st.set_page_config(page_title="2026 台股波段策略掃描器", layout="wide")

@st.cache_data(ttl=3600)
def get_stock_list():
    """讀取台股清單 (需準備 taiwan_stock_list.csv)"""
    cache_file = "taiwan_stock_list.csv"
    fallback = {"2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科"}
    
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

# --- 2. 波段 SOP 技術分析引擎 ---
def analyze_sop_strategy(df, symbol, name):
    try:
        if df is None or len(df) < 70: return None
        
        # 統一處理 yfinance 多層索引
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # 計算指標
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
        
        # 【選股條件】：20MA > 60MA (多頭排列)
        if not (curr['MA20'] > curr['MA60']): return None

        # 【進場條件 A】：帶量突破壓力 (過昨高 + 量 > 1.5倍均量)
        is_breakout = (curr['Close'] > prev['High']) and (curr['Volume'] > curr['VMA20'] * 1.5)
        
        # 【進場條件 B】：回測均線不破 + MACD 紅柱 (回測月線 2% 內 + 紅柱)
        is_support = (curr['Low'] <= curr['MA20'] * 1.02) and (curr['Close'] >= curr['MA20'] * 0.98) and (hist.iloc[-1] > 0)

        if is_breakout or is_support:
            return {
                "股票": f"{symbol.split('.')[0]} {name}",
                "型態": "🚀 帶量突破" if is_breakout else "📉 回測支撐",
                "現價": round(curr['Close'], 2),
                "月線價 (20MA)": round(curr['MA20'], 2),
                "MACD 狀態": "🔴 紅柱續強" if hist.iloc[-1] > hist.iloc[-2] else "⚪ 紅柱轉弱",
                "成交量": "🔥 爆量" if curr['Volume'] > curr['VMA20'] * 1.5 else "正常",
                "出場防守點": round(curr['MA20'] * 0.98, 2) # 跌破月線約 2% 出場
            }
    except: return None
    return None

# --- 3. UI 介面與加速分析邏輯 ---
st.title("⚡ TW 2026 波段 SOP 精確掃描器")

stock_dict = get_stock_list()
symbols = list(stock_dict.keys())

with st.sidebar:
    st.header("⚙️ 策略參數確認")
    st.success("✅ 多頭排列: 20MA > 60MA")
    st.info(f"📊 待掃描清單: {len(symbols)} 檔")
    start_btn = st.button("🚀 啟動加速分析", use_container_width=True)

if start_btn:
    all_results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    start_time = time.time()
    
    with st.spinner("📦 正在抓取大數據並進行波段過濾..."):
        # 關閉多執行緒以相容 Python 3.13，提升穩定性
        raw_data = yf.download(symbols, period="6mo", group_by='ticker', threads=False, progress=False)
        
        total = len(symbols)
        for idx, (sym, name) in enumerate(stock_dict.items()):
            try:
                stock_df = raw_data[sym] if total > 1 else raw_data
                if stock_df.empty: continue
                
                res = analyze_sop_strategy(stock_df, sym, name)
                if res: all_results.append(res)
            except: continue
            
            # 更新進度條與預估剩餘時間
            if (idx + 1) % 5 == 0 or (idx + 1) == total:
                percent = (idx + 1) / total
                elapsed = time.time() - start_time
                avg_time = elapsed / (idx + 1)
                rem_time = avg_time * (total - (idx + 1))
                
                progress_bar.progress(percent)
                status_text.markdown(f"**進度:** `{percent:.1%}` | **已分析:** `{idx+1}/{total}` | **預計剩餘:** `{rem_time:.0f} 秒`")

    status_text.success(f"✅ 掃描完成！總耗時: {time.time() - start_time:.1f} 秒")

    if all_results:
        st.subheader(f"🎯 波段進場訊號 (發現 {len(all_results)} 檔)")
        
        # 依型態排序：突破型排在前面，方便追蹤動能
        df_res = pd.DataFrame(all_results).sort_values(by=["型態", "現價"], ascending=[False, True])
        
        st.dataframe(
            df_res, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "現價": st.column_config.NumberColumn(format="%.2f"),
                "月線價 (20MA)": st.column_config.NumberColumn(format="%.2f"),
                "出場防守點": st.column_config.NumberColumn(format="%.2f", help="跌破此位建議波段出場")
            }
        )
    else:
        st.warning("目前盤面上查無符合 20MA>60MA 且帶量突破或回測支撐的標的。")

st.divider()
st.caption("策略提醒：本系統僅供技術線型參考，波段交易請務必搭配成交量與三大法人籌碼面觀察。")
