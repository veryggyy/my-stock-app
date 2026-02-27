import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time
import os
from datetime import datetime

# --- 1. 頁面設定 ---
st.set_page_config(page_title="2026 精準波段 SOP 掃描器", layout="wide")

# 自定義手機版 CSS (隱藏不必要的空白)
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    .stProgress > div > div > div > div { background-color: #00ffcc; }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_stock_list():
    # 內建台灣前 20 大權值股，確保沒檔案也能跑
    default_list = {
        "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", 
        "2308.TW": "台達電", "2382.TW": "廣達", "2881.TW": "富邦金",
        "2882.TW": "國泰金", "2303.TW": "聯電", "3711.TW": "日月光",
        "2412.TW": "中華電", "2886.TW": "兆豐金", "2603.TW": "長榮",
        "3008.TW": "大立光", "2357.TW": "華碩", "3231.TW": "緯創"
    }
    cache_file = "taiwan_stock_list.csv"
    if os.path.exists(cache_file):
        try:
            df = pd.read_csv(cache_file, dtype=str, encoding='utf-8-sig')
            c_col = next((c for c in df.columns if any(k in c for k in ['Symbol', '代號', 'code'])), df.columns[0])
            n_col = next((c for c in df.columns if any(k in c for k in ['Name', '名稱', 'label'])), df.columns[1])
            return {f"{str(row[c_col]).strip()[:4]}.TW": str(row[n_col]).strip() for _, row in df.iterrows()}
        except: return default_list
    return default_list

# --- 2. 核心 SOP 分析引擎 ---
def analyze_2026_sop(df, vol_mult):
    if df is None or len(df) < 60: return None
    
    # 計算指標
    df['MA20'] = ta.sma(df['Close'], length=20)
    df['MA60'] = ta.sma(df['Close'], length=60)
    df['VMA20'] = ta.sma(df['Volume'], length=20)
    
    macd = ta.macd(df['Close'])
    df['MACD_h'] = macd['MACDh_12_26_9']
    
    kd = ta.stoch(df['High'], df['Low'], df['Close'])
    df['K'] = kd['STOCHk_14_3_3']
    df['D'] = kd['STOCHd_14_3_3']

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # 【SOP 條件】
    # 1. 趨勢：站穩 20/60MA
    is_bullish = curr['Close'] > curr['MA20'] and curr['Close'] > curr['MA60']
    
    # 2. 進場 A：帶量 + MACD 轉正 (放寬判斷：轉正或是正值剛開始放大)
    is_breakout = (curr['Volume'] > curr['VMA20'] * vol_mult) and \
                  ((curr['MACD_h'] > 0 >= prev['MACD_h']) or (curr['MACD_h'] > prev['MACD_h'] > 0))
    
    # 3. 進場 B：KD 低檔金叉 (K < 35)
    is_kd_cross = (prev['K'] < 35) and (curr['K'] > curr['D']) and (prev['K'] <= prev['D'])

    if is_bullish and (is_breakout or is_kd_cross):
        return {
            "型態": "🚀 帶量轉強" if is_breakout else "🎯 KD 低檔金叉",
            "現價": round(curr['Close'], 2),
            "MA20": round(curr['MA20'], 2),
            "量能": f"{round(curr['Volume']/curr['VMA20'], 1)}x",
            "KD值": f"K:{int(curr['K'])}",
            "防守點": round(min(curr['MA20'], curr['Low'] * 0.98), 2),
            "優先級": 1 if is_breakout else 2
        }
    return None

# --- 3. UI 介面 ---
st.title("⚡ 2026 SOP 掃描器")
st.caption(f"📅 當前時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

stock_dict = get_stock_list()
symbols = list(stock_dict.keys())

with st.sidebar:
    st.header("⚙️ 掃描設定")
    vol_target = st.slider("成交量倍數門檻", 0.5, 3.0, 1.0, 0.1)
    st.info("💡 若找不到標的，請將門檻調低至 0.8~1.0")
    if st.button("🔄 清除快取"):
        st.cache_data.clear()
    start_btn = st.button("🚀 開始掃描", use_container_width=True)

if start_btn:
    results = []
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    start_time = time.time()
    
    # 批次下載數據
    with st.spinner('連線 Yahoo Finance 下載數據中...'):
        data = yf.download(symbols, period="6mo", group_by='ticker', threads=True, progress=False)
    
    total = len(symbols)
    for idx, (sym, name) in enumerate(stock_dict.items()):
        # 計算進度百分比與 ETA
        processed = idx + 1
        percent = int((processed / total) * 100)
        elapsed = time.time() - start_time
        eta = int((elapsed / processed) * (total - processed)) if processed > 0 else 0
        
        status_text.markdown(f"**掃描進度：{percent}%** | 預計剩餘：`{eta}` 秒")
        progress_bar.progress(processed / total)
        
        try:
            # 取得該股 DataFrame
            if total > 1:
                stock_df = data[sym].dropna()
            else:
                stock_df = data.dropna()
                
            res = analyze_2026_sop(stock_df, vol_target)
            if res:
                res["股票"] = f"{sym.split('.')[0]} {name}"
                results.append(res)
        except: continue

    status_text.success(f"✅ 掃描完成！費時 {int(time.time() - start_time)} 秒")

    # --- 4. 手機優化結果呈現 ---
    if results:
        st.subheader(f"🎯 符合 SOP 標的 ({len(results)})")
        # 按優先級排序
        sorted_results = sorted(results, key=lambda x: x['優先級'])
        
        for item in sorted_results:
            with st.container(border=True):
                # 第一欄：股票名稱與訊號
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.markdown(f"### {item['股票']}")
                    st.write(f"**{item['型態']}**")
                with col2:
                    st.metric("現價", item['現價'])
                
                # 第二欄：關鍵數據
                d1, d2, d3 = st.columns(3)
                d1.caption("📊 量能")
                d1.write(f"`{item['量能']}`")
                d2.caption("📈 KD值")
                d2.write(f"`{item['KD值']}`")
                d3.caption("🛡️ 防守")
                d3.write(f"**{item['防守點']}**")
    else:
        st.warning("⚠️ 目前無符合條件之標的。建議調低「成交量倍數門檻」或檢查網路連線。")

st.divider()
st.caption("⚠ 免責聲明：本工具僅供 2026 技術分析參考，投資請嚴格執行停損。")
