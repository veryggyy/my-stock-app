import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os

# --- 1. 頁面設定 ---
st.set_page_config(page_title="2026 趨勢波段掃描系統", layout="wide")

@st.cache_data(ttl=3600)
def get_stock_list():
    """CSV 讀取與自動校正"""
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

# --- 2. 核心技術分析 (多頭排列 + 進場過濾) ---
def advanced_analyze(data, symbol, name):
    try:
        if data is None or len(data) < 70: return None # 需足夠 K 線計算 60MA
        df = data.copy()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 指標計算
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        df['VMA20'] = df['Volume'].rolling(20).mean()
        
        # MACD 計算
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # --- 策略篩選 ---
        # 1. 選股：20MA > 60MA (多頭排列)
        is_bull = curr['MA20'] > curr['MA60']
        if not is_bull: return None

        # 2. 進場判斷：
        # A. 帶量突破 (今日收盤 > 昨日高點 且 量 > 20日均量1.5倍)
        is_breakout = (curr['Close'] > prev['High']) and (curr['Volume'] > curr['VMA20'] * 1.5)
        # B. 回測月線不破 且 MACD 紅柱
        is_support = (curr['Low'] <= curr['MA20'] * 1.02) and (curr['Close'] >= curr['MA20']) and (hist.iloc[-1] > 0)

        if is_breakout or is_support:
            return {
                "代號": symbol.split('.')[0],
                "股票名稱": name,
                "現價": round(curr['Close'], 2),
                "短中期買進價位": round(curr['MA20'], 2), # 建議於月線附近佈局
                "波段目標/賣出價": round(curr['Close'] * 1.15, 2), # 設定 15% 為初步目標
                "出場防守位": round(curr['MA20'] * 0.97, 2), # 跌破月線 3% 視為轉弱
                "型態": "🚀 帶量突破" if is_breakout else "📉 回測支撐",
                "MACD": "🔴 紅柱" if hist.iloc[-1] > 0 else "🟢 綠柱",
                "成交量": "🔥 爆量" if curr['Volume'] > curr['VMA20'] * 1.5 else "正常"
            }
    except: return None
    return None

# --- 3. UI 介面 ---
st.title("⚡ TW 2026 極速趨勢波段掃描器")
stock_dict = get_stock_list()
symbols = list(stock_dict.keys())

with st.sidebar:
    st.header("⚙️ 策略參數")
    st.info("策略規則：\n1. 20MA > 60MA\n2. 帶量突破 或 回測月線\n3. 跌破 20MA 則波段結束")
    st.write(f"📊 待掃描清單: {len(symbols)} 檔")
    start_btn = st.button("🚀 執行策略掃描")

if start_btn:
    all_results = []
    progress_bar = st.progress(0)
    
    with st.spinner(f"正在分析波段標的..."):
        # 下載半年資料以計算 60MA
        raw_data = yf.download(symbols, period="8mo", group_by='ticker', threads=True, progress=False)
        
        for idx, (sym, name) in enumerate(stock_dict.items()):
            stock_df = raw_data[sym] if len(symbols) > 1 else raw_data
            if stock_df.empty: continue
            
            res = advanced_analyze(stock_df, sym, name)
            if res: all_results.append(res)
            
            if idx % 50 == 0: progress_bar.progress(min((idx + 1) / len(symbols), 1.0))
        progress_bar.progress(1.0)

    if all_results:
        st.success(f"發現 {len(all_results)} 檔符合「多頭排列 + 進場訊號」標的")
        df_res = pd.DataFrame(all_results).sort_values(by="現價")
        st.dataframe(df_res, use_container_width=True, hide_index=True)
    else:
        st.warning("目前市場無符合多頭回測條件之標的。")

st.markdown("---")
st.caption("策略備註：出場建議參考 MACD 高檔死叉或收盤價跌破月線（20MA）。")
