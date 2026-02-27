import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
import time  # 新增：用於計算剩餘時間

# --- 1. 頁面設定 ---
st.set_page_config(page_title="2026 台股趨勢波段掃描器", layout="wide")

@st.cache_data(ttl=3600)
def get_stock_list():
    """超強健 CSV 讀取與自動校正"""
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
        
        if df.empty: return fallback
        return {f"{row['clean_code']}.TW": str(row[name_col]).strip() for _, row in df.iterrows()}
    except: return fallback

# --- 2. 核心技術分析 ---
def analyze_trend_strategy(data, symbol, name):
    try:
        if data is None or len(data) < 70: return None
        
        df = data.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['VMA20'] = df['Volume'].rolling(window=20).mean()
        
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        hist = macd_line - signal_line

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        if not (curr['MA20'] > curr['MA60']): return None

        is_breakout = (curr['Close'] > prev['High']) and (curr['Volume'] > curr['VMA20'] * 1.5)
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
    st.markdown("""
    **🎯 核心規則：**
    1. **多頭排列**：20MA > 60MA
    2. **進場點**：帶量突破壓力 或 回測月線不破
    3. **出場點**：跌破 20MA 或 MACD 死叉
    """)
    st.info(f"📊 待掃描清單: {len(symbols)} 檔")
    start_btn = st.button("🚀 啟動穩定版掃描")

if start_btn:
    all_results = []
    progress_bar = st.progress(0)
    status_text = st.empty() # 動態顯示進度文字
    
    start_time = time.time() # 紀錄開始時間
    
    try:
        # 下載數據
        with st.spinner("📦 正在從 Yahoo Finance 下載數據..."):
            raw_data = yf.download(symbols, period="8mo", group_by='ticker', threads=False, progress=False)
        
        # 逐檔分析
        total = len(symbols)
        for idx, (sym, name) in enumerate(stock_dict.items()):
            try:
                stock_df = raw_data[sym] if len(symbols) > 1 else raw_data
                if stock_df.empty or len(stock_df) < 60: continue
                
                res = analyze_trend_strategy(stock_df, sym, name)
                if res: all_results.append(res)
            except: continue
            
            # 更新進度條與預估時間
            processed = idx + 1
            percent = processed / total
            elapsed_time = time.time() - start_time
            avg_time_per_stock = elapsed_time / processed
            remaining_time = avg_time_per_stock * (total - processed)
            
            progress_bar.progress(percent)
            status_text.text(f"🚀 進度: {percent:.1%} ({processed}/{total}) | 預計剩餘時間: {remaining_time:.0f} 秒")
        
        status_text.success(f"✅ 掃描完成！總耗時: {time.time() - start_time:.1f} 秒")
        
    except Exception as e:
        st.error(f"掃描中斷: {e}")

    if all_results:
        st.success(f"發現 {len(all_results)} 檔符合策略標的")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("#### 🟢 型態解釋")
            st.caption("🚀 **帶量突破**：價格過昨高且量能放大。")
            st.caption("📉 **回測支撐**：回檔至月線附近守穩。")
        with col2:
            st.markdown("#### 🔴 MACD 指標")
            st.caption("🔴 **紅柱**：多方動能增強。")
        with col3:
            st.markdown("#### 📊 成交量")
            st.caption("🔥 **爆量**：大於 20 日均量 1.5 倍。")
        
        st.divider()
        
        # 顯示結果表格，依型態與現價排序，讓買進訊號最明確的靠前
        df_res = pd.DataFrame(all_results).sort_values(by=["型態", "現價"], ascending=[False, True])
        st.dataframe(df_res, use_container_width=True, hide_index=True)
    else:
        st.warning("查無符合多頭排列與進場條件的股票。")

st.markdown("---")
st.caption("修復紀錄：已加入即時預估時間演算法，並優化結果排列順序。")
