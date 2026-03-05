import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time
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
    .stProgress > div > div > div > div { background-color: #00ffcc; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 獲取全台股清單 (修正格式防呆) ---
@st.cache_data(ttl=86400)
def get_full_taiwan_list():
    stocks = {}
    api_urls = [
        'https://openapi.twse.com.tw',
        'https://openapi.twse.com.tw'
    ]
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    success = False
    for url in api_urls:
        try:
            response = requests.get(url, timeout=10, verify=False, headers=headers)
            if response.status_code == 200:
                res = response.json()
                for s in res:
                    code = str(s.get('Code') or s.get('SecId') or '')
                    name = s.get('Name') or s.get('SecName') or ''
                    if len(code) == 4:
                        stocks[f"{code}.TW"] = name
                if len(stocks) > 50:
                    success = True
                    break
        except:
            continue

    if success:
        # 加入必備上櫃標的
        tpex = {"8069.TWO": "元太", "6488.TWO": "環球晶", "5274.TWO": "信驊", "3293.TWO": "鈊象", "6138.TWO": "茂達"}
        stocks.update(tpex)
        return stocks, "Online"
    else:
        # 內建離線權值股 (確保格式為清單)
        offline = {"2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2382.TW": "廣達", "2603.TW": "長榮", "2308.TW": "台達電"}
        return offline, "Offline"

# --- 3. 核心 SOP 分析引擎 ---
def analyze_sop_v4(df, vol_mult, kd_threshold):
    try:
        if df is None or len(df) < 35: return None
        # 計算指標
        df['MA20'] = ta.sma(df['Close'], length=20)
        df['VMA20'] = ta.sma(df['Volume'], length=20)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        kd = ta.stoch(df['High'], df['Low'], df['Close'])
        df['K'], df['D'] = kd['STOCHk_14_3_3'], kd['STOCHd_14_3_3']
        
        curr, prev = df.iloc[-1], df.iloc[-2]
        
        # 邏輯過濾
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
    return None

# --- 4. 主介面 ---
st.title("⚡ 2026 全台股 SOP 掃描")
st.caption(f"📅 系統時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

with st.sidebar:
    st.header("⚙️ 參數設定")
    vol_target = st.slider("1. 量能倍數", 0.5, 3.0, 1.0, 0.1)
    kd_limit = st.slider("2. KD 門檻", 20, 85, 55, 5)
    scan_limit = st.number_input("3. 掃描檔數", 10, 2500, 1000)
    if st.button("🔄 清除快取"):
        st.cache_data.clear()
        st.rerun()

# --- 5. 執行分析 ---
if st.button("🔵 開始分析符合標的", use_container_width=True):
    all_stocks, mode = get_full_taiwan_list()
    if mode == "Offline": st.warning("⚠️ 證交所 API 連線失敗，目前掃描內建權值股。")
    
    # 修正：確保 tickers 是純 list 格式
    raw_items = list(all_stocks.items())[:int(scan_limit)]
    tickers = [item[0] for item in raw_items]
    
    results = []
    progress_bar = st.progress(0)

    with st.spinner('同步市場數據中...'):
        # 修正：yf.download 的正確調用方式
        data = yf.download(tickers, period="6mo", interval="1d", group_by='ticker', auto_adjust=True, progress=False)

    for idx, (sym, name) in enumerate(raw_items):
        progress_bar.progress((idx + 1) / len(raw_items))
        try:
            # 處理單檔與多檔數據提取
            df = data[sym] if len(tickers) > 1 else data
            df = df.dropna()
            if len(df) < 20: continue
            
            res = analyze_sop_v4(df, vol_target, kd_limit)
            if res:
                res["股票"] = f"{sym.replace('.TW','').replace('.TWO','')} {name}"
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
    else:
        st.error("❌ 目前條件下無符合標的。")

st.divider()
st.caption("⚠ 免責聲明：僅供參考，投資請自行評估風險。")
