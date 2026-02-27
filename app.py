import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time
import requests
from datetime import datetime

# --- 1. 頁面設定：強制居中與大字體 CSS ---
st.set_page_config(page_title="2026 全台股 SOP 掃描", layout="centered")

st.markdown("""
    <style>
    /* 螢幕居中優化 */
    .block-container { padding-top: 2rem; max-width: 500px; }
    
    /* 大字體與視覺強化 */
    h3 { font-size: 2.2rem !important; font-weight: 800; color: #FFFFFF; margin-bottom: 5px; }
    .stMetric { background-color: #0e1117; padding: 15px; border-radius: 10px; }
    [data-testid="stMetricValue"] { font-size: 2.8rem !important; color: #00FFCC !important; font-weight: 900; }
    
    /* 訊息框大字體 */
    .stAlert p { font-size: 1.3rem !important; font-weight: bold; }
    
    /* 價格建議區塊 */
    .price-box {
        font-size: 1.4rem;
        line-height: 2.2;
        font-weight: bold;
        padding: 10px;
        border-top: 1px solid #374151;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. 獲取全台股清單 (上市/上櫃) ---
@st.cache_data(ttl=86400)
def get_full_taiwan_list():
    stocks = {}
    try:
        # 上市公司
        twse = requests.get('https://openapi.twse.com.tw').json()
        for s in twse: stocks[f"{s['Code']}.TW"] = s['Name']
        # 上櫃公司 (主要標的示意，可依需求擴充 API)
        tpex_list = {"8069.TWO": "元太", "6488.TWO": "環球晶", "5274.TWO": "信驊", "3293.TWO": "鈊象"}
        stocks.update(tpex_list)
    except:
        return {"2330.TW": "台積電", "2317.TW": "鴻海"}
    return stocks

# --- 3. SOP 分析引擎 ---
def analyze_sop_2026(df, vol_mult):
    if len(df) < 60: return None
    
    # 計算關鍵指標
    df['MA20'] = ta.sma(df['Close'], length=20)
    df['MA60'] = ta.sma(df['Close'], length=60)
    df['VMA20'] = ta.sma(df['Volume'], length=20)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    macd = ta.macd(df['Close'])
    df['MACD_h'] = macd['MACDh_12_26_9']
    kd = ta.stoch(df['High'], df['Low'], df['Close'])
    df['K'], df['D'] = kd['STOCHk_14_3_3'], kd['STOCHd_14_3_3']

    curr, prev = df.iloc[-1], df.iloc[-2]

    # 篩選條件：站穩月/季線
    if not (curr['Close'] > curr['MA20'] and curr['Close'] > curr['MA60']): return None

    is_vol = curr['Volume'] > curr['VMA20'] * vol_mult
    is_macd = curr['MACD_h'] > prev['MACD_h']
    is_kd = (prev['K'] < 45) and (curr['K'] > curr['D'])

    if (is_vol and is_macd) or is_kd:
        # 排序權重：1(最優) 到 3
        rank = 1 if (is_vol and is_kd) else (2 if is_vol else 3)
        
        # 建議價格策略
        return {
            "優劣": rank,
            "訊號": "🚀 攻擊 (帶量)" if rank <= 2 else "🎯 轉強 (金叉)",
            "現價": round(curr['Close'], 2),
            "量比": round(curr['Volume']/curr['VMA20'], 1),
            "建議買進": round(curr['MA20'] * 1.01, 2),
            "波段賣出": round(curr['Close'] + (df['ATR'].iloc[-1] * 3), 2),
            "關鍵支撐": round(min(curr['MA20'], curr['Low'] * 0.98), 2)
        }
    return None

# --- 4. 主程式 UI ---
st.title("⚡ 2026全台股SOP掃描")
st.caption("目前模式：手機直式大字體 | 2026-02-27")

with st.sidebar:
    st.header("⚙️ 設定")
    vol_target = st.slider("量能標準 (預設1.1)", 0.5, 3.0, 1.1)
    # 預設全掃描 (設定為 2000)
    scan_limit = st.number_input("掃描桿的數 (預設全掃描)", 10, 2000, 2000)

if st.button("🔵 開始攝影分析", use_container_width=True):
    all_stocks = get_full_taiwan_list()
    scan_items = list(all_stocks.items())[:scan_limit]
    
    results = []
    prog_text = st.empty()
    bar = st.progress(0)
    start_time = time.time()

    # 批次獲取數據
    data = yf.download([s[0] for s in scan_items], period="6mo", group_by='ticker', threads=True, progress=False)

    for idx, (sym, name) in enumerate(scan_items):
        # 計算進度與 ETA
        processed = idx + 1
        pct = processed / len(scan_items)
        elapsed = time.time() - start_time
        eta = int((elapsed / processed) * (len(scan_items) - processed))
        
        prog_text.markdown(f"**⌛ 掃描中: {int(pct*100)}% | 剩餘: {eta}秒**")
        bar.progress(pct)
        
        try:
            df = data[sym].dropna()
            res = analyze_sop_2026(df, vol_target)
            if res:
                res["股票"] = f"{sym.split('.')[0]} {name}"
                results.append(res)
        except: continue

    prog_text.empty()
    bar.empty()

    if results:
        sorted_res = sorted(results, key=lambda x: x['優劣'])
        st.success(f"✅ 掃描完成！找到 {len(results)} 檔符合標準的")
        
        for item in sorted_res:
            with st.container(border=True):
                st.write(f"### {item['股票']}")
                st.info(f"訊息: {item['訊號']}")
                
                c1, c2 = st.columns([2, 1])
                c1.metric("目前價格", f"{item['現價']}")
                c2.write(f"📊 量比：{item['量比']}x")
                
                st.markdown(f"""
                <div class="price-box">
                🟢 建議買進：<span style="color:#00FF88;">{item['建議買進']}</span><br>
                🔴 波段賣出：<span style="color:#FF4B4B;">{item['波段賣出']}</span><br>
                🔵 關鍵支撐：<span style="color:#4FACFE;">{item['關鍵支撐']}</span>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.warning("當前無符合標的，請嘗試調低量能標準。")

st.divider()
st.caption("管理通用：本工具僅供 2026 技術面參考，操作請嚴格執行停損。")
