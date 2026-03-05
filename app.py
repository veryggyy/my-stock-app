import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import urllib3
from datetime import datetime

# 隱藏 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. 頁面設定 ---
st.set_page_config(page_title="2026 全台股 SOP 掃描", layout="centered")

st.markdown("""
    <style>
    .block-container { padding-top: 1rem; max-width: 500px; }
    h3 { font-size: 2.2rem !important; font-weight: 800; color: #FFD700; margin-bottom: 5px; }
    [data-testid="stMetricValue"] { font-size: 3rem !important; color: #00FFCC !important; font-weight: 900; }
    .guide-box { background-color: #1e293b; padding: 15px; border-radius: 12px; border-left: 6px solid #3b82f6; margin-bottom: 20px; font-size: 1.1rem; }
    .price-box { font-size: 1.5rem; line-height: 2.2; font-weight: bold; padding: 12px; background: #0f172a; border-radius: 10px; border: 1px solid #374151; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 獲取全台股清單 (手動逐行解析 CSV，最穩定) ---
@st.cache_data(ttl=600) # 10分鐘更新一次
def get_full_taiwan_list():
    stocks = {}
    try:
        # 直接抓取 GitHub CSV 原始文字內容
        csv_url = "https://raw.githubusercontent.com"
        resp = requests.get(f"{csv_url}?v={datetime.now().timestamp()}", timeout=10)
        
        if resp.status_code == 200:
            # 將內容拆成一行一行來讀取，避開 pandas 的解析錯誤
            lines = resp.text.strip().splitlines()
            for line in lines:
                # 嘗試用半形逗號分割
                parts = line.split(',')
                if len(parts) >= 2:
                    code = parts[0].strip().upper()
                    name = parts[1].strip()
                    # 過濾掉標題行和無效行
                    if "代號" not in code and len(code) >= 4:
                        # 自動修正：如果沒帶後綴，補上 .TW
                        if not (code.endswith('.TW') or code.endswith('.TWO')):
                            code = f"{code}.TW"
                        stocks[code] = name
            
            if len(stocks) > 0:
                return stocks, "📡 已成功載入您的 CSV 股票清單"
    except Exception as e:
        st.sidebar.error(f"讀取錯誤: {str(e)}")
    
    # 最終保底
    return {"2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科"}, "⚠️ 使用內建保底清單"

# --- 3. 核心 SOP 分析 ---
def analyze_sop_v4(df, vol_mult, kd_threshold):
    try:
        if df is None or len(df) < 35: return None
        # 確保數據清理
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].apply(pd.to_numeric, errors='coerce').dropna()
        if len(df) < 30: return None
        
        df['MA20'] = ta.sma(df['Close'], length=20)
        df['VMA20'] = ta.sma(df['Volume'], length=20)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        kd = ta.stoch(df['High'], df['Low'], df['Close'])
        df['K'], df['D'] = kd['STOCHk_14_3_3'], kd['STOCHd_14_3_3']
        curr, prev = df.iloc[-1], df.iloc[-2]
        
        if curr['Close'] < (curr['MA20'] * 0.97): return None
        is_vol = (curr['Volume'] > curr['VMA20'] * vol_mult)
        is_kd = (prev['K'] < kd_threshold) and (curr['K'] > curr['D'])

        if is_vol or is_kd:
            rank = 1 if (is_vol and is_kd) else (2 if is_vol else 3)
            return {
                "優劣": rank, "訊號": "🔥 帶量金叉" if rank == 1 else ("🚀 攻擊 (帶量)" if rank == 2 else "🎯 轉強 (金叉)"),
                "現價": round(float(curr['Close']), 2), "量比": round(float(curr['Volume'] / curr['VMA20']), 2),
                "K值": int(curr['K']), "建議買進": round(float(curr['MA20']), 2),
                "波段賣出": round(float(curr['Close'] + (df['ATR'].iloc[-1] * 2.5)), 2),
                "關鍵支撐": round(float(min(curr['MA20'], curr['Low'])), 2)
            }
    except: return None

# --- 4. 主介面 ---
st.title("⚡ 2026 全台股 SOP 掃描")
st.caption(f"📅 系統時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

with st.sidebar:
    st.header("⚙️ 參數設定")
    vol_target = st.slider("1. 量能倍數", 0.5, 3.0, 1.0, 0.1)
    kd_limit = st.slider("2. KD 門檻", 20, 85, 55, 5)
    scan_limit = st.number_input("3. 掃描檔數", 10, 2500, 1000)
    if st.button("🔄 清除快取並重啟"):
        st.cache_data.clear()
        st.rerun()

# --- 5. 執行分析 ---
if st.button("🔵 開始分析符合標的", use_container_width=True):
    all_stocks, status_msg = get_full_taiwan_list()
    st.info(status_msg)
    
    tickers = sorted(list(all_stocks.keys()))[:int(scan_limit)]
    
    if not tickers:
        st.error("清單為空，請檢查 CSV 內容。")
    else:
        results = []
        progress_bar = st.progress(0)
        with st.spinner('同步市場數據中...'):
            data = yf.download(tickers, period="6mo", group_by='ticker', auto_adjust=True, progress=False)

        for idx, sym in enumerate(tickers):
            progress_bar.progress((idx + 1) / len(tickers))
            try:
                df = data[sym].dropna() if len(tickers) > 1 else data.dropna()
                if len(df) < 20: continue
                res = analyze_sop_v4(df, vol_target, kd_limit)
                if res:
                    res["股票"] = f"{sym.split('.')[0]} {all_stocks[sym]}"
                    results.append(res)
            except: continue
        
        progress_bar.empty()
        if results:
            for item in sorted(results, key=lambda x: x['優劣']):
                with st.container(border=True):
                    st.write(f"### {item['股票']}")
                    st.info(f"訊號：{item['訊號']}")
                    c1, c2 = st.columns(2)
                    c1.metric("目前價格", f"{item['現價']}")
                    c2.write(f"📊 量比：`{item['量比']}x` \n\n📈 K值：`{item['K值']}`")
                    st.markdown(f'<div class="price-box">🟢 建議買進：<span style="color:#00FF88;">{item["建議買進"]}</span><br>🔴 波段賣出：<span style="color:#FF4B4B;">{item["波段賣出"]}</span><br>🔵 關鍵支撐：<span style="color:#4FACFE;">{item["關鍵支撐"]}</span></div>', unsafe_allow_html=True)
        else: st.error("❌ 目前條件下無符合標的。")

st.divider()
st.caption("⚠ 投資盈虧自負。")
