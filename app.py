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

# --- 2. 核心技術分析 ---
def advanced_analyze(data, symbol, name):
    try:
        if data is None or len(data) < 70: return None
        df = data.copy()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        df['VMA20'] = df['Volume'].rolling(20).mean()
        
        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 策略過濾：20MA > 60MA
        if not (curr['MA20'] > curr['MA60']): return None

        # A. 帶量突破 (收盤 > 昨日高點 且 量 > 1.5倍均量)
        is_breakout = (curr['Close'] > prev['High']) and (curr['Volume'] > curr['VMA20'] * 1.5)
        # B. 回測支撐 (低點碰到月線附近 且 MACD 紅柱)
        is_support = (curr['Low'] <= curr['MA20'] * 1.02) and (curr['Close'] >= curr['MA20'] * 0.99) and (hist.iloc[-1] > 0)

        if is_breakout or is_support:
            return {
                "代號": symbol.split('.')[0],
                "股票名稱": name,
                "現價": round(curr['Close'], 2),
                "短中期買進價位": round(curr['MA20'], 2),
                "波段目標/賣出價": round(curr['Close'] * 1.15, 2),
                "出場防守位": round(curr['MA20'] * 0.97, 2),
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
    st.info("🎯 **核心規則**：\n1. **多頭排列**：20MA > 60MA\n2. **進場點**：帶量突破壓力 或 回測月線不破\n3. **出場點**：跌破 20MA 或 MACD 死叉")
    st.write(f"📊 待掃描清單: {len(symbols)} 檔")
    start_btn = st.button("🚀 執行策略掃描")

if start_btn:
    all_results = []
    progress_bar = st.progress(0)
    
    with st.spinner(f"正在掃描台股波段標的..."):
        raw_data = yf.download(symbols, period="8mo", group_by='ticker', threads=True, progress=False)
        for idx, (sym, name) in enumerate(stock_dict.items()):
            stock_df = raw_data[sym] if len(symbols) > 1 else raw_data
            if stock_df.empty: continue
            res = advanced_analyze(stock_df, sym, name)
            if res: all_results.append(res)
            if idx % 100 == 0: progress_bar.progress(min((idx + 1) / len(symbols), 1.0))
        progress_bar.progress(1.0)

    if all_results:
        # --- 新增技術名稱解釋區 ---
        st.success(f"發現 {len(all_results)} 檔符合策略標的")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("#### 🟢 型態解釋")
            st.caption("🚀 **帶量突破**：價格過昨高且成交量放大，具攻擊動能。")
            st.caption("📉 **回測支撐**：股價回落至月線附近守穩，低吸機會。")
        with col2:
            st.markdown("#### 🔴 MACD 指標")
            st.caption("🔴 **紅柱**：多方動能持續，直方圖大於 0。")
            st.caption("🟢 **綠柱**：多方動能轉弱，需注意死叉風險。")
        with col3:
            st.markdown("#### 📊 成交量")
            st.caption("🔥 **爆量**：今日成交量大於 20 日平均量 1.5 倍。")
            st.caption("⚪ **正常**：成交量維持常態，無過熱跡象。")
        
        st.divider() # 分隔線
        
        # 顯示結果表格
        df_res = pd.DataFrame(all_results).sort_values(by="現價")
        st.dataframe(df_res, use_container_width=True, hide_index=True)
    else:
        st.warning("目前市場無符合條件之標的。")

st.markdown("---")
st.caption("注意：本工具僅供參考，不構成投資建議。")
