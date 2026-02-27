import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time
import requests
from datetime import datetime

# --- 1. 頁面設定與直式大字體 ---
st.set_page_config(page_title="2026 全台股 SOP 掃描", layout="centered")

st.markdown("""
    <style>
    .block-container { padding-top: 1rem; max-width: 550px; }
    h3 { font-size: 2rem !important; font-weight: 800; color: #FFD700; }
    [data-testid="stMetricValue"] { font-size: 2.6rem !important; color: #00FFCC !important; }
    .stSlider [data-baseweb="slider"] { margin-bottom: 20px; }
    .guide-box {
        background-color: #1e293b;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #3b82f6;
        margin-bottom: 20px;
        font-size: 0.95rem;
    }
    .price-box {
        font-size: 1.3rem;
        line-height: 2;
        font-weight: bold;
        padding: 10px;
        background: #0f172a;
        border-radius: 8px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. 獲取清單與分析引擎 ---
@st.cache_data(ttl=86400)
def get_full_taiwan_list():
    stocks = {}
    try:
        res = requests.get('https://openapi.twse.com.tw').json()
        for s in res: stocks[f"{s['Code']}.TW"] = s['Name']
        # 加入熱門上櫃標的
        stocks.update({"8069.TWO": "元太", "6488.TWO": "環球晶", "5274.TWO": "信驊"})
    except: return {"2330.TW": "台積電", "2317.TW": "鴻海"}
    return stocks

def analyze_sop_v3(df, vol_mult, kd_threshold):
    if len(df) < 60: return None
    
    # 指標計算
    df['MA20'] = ta.sma(df['Close'], length=20)
    df['MA60'] = ta.sma(df['Close'], length=60)
    df['VMA20'] = ta.sma(df['Volume'], length=20)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    macd = ta.macd(df['Close'])
    df['MACD_h'] = macd['MACDh_12_26_9']
    kd = ta.stoch(df['High'], df['Low'], df['Close'])
    df['K'], df['D'] = kd['STOCHk_14_3_3'], kd['STOCHd_14_3_3']

    curr, prev = df.iloc[-1], df.iloc[-2]

    # 基礎門檻：站穩月線 (20MA)
    if not (curr['Close'] > curr['MA20']): return None

    # 訊號 A：帶量攻擊 (成交量 > 20日均量 * 倍數)
    is_vol = curr['Volume'] > curr['VMA20'] * vol_mult
    # 訊號 B：KD 金叉 (K值需低於設定門檻)
    is_kd = (prev['K'] < kd_threshold) and (curr['K'] > curr['D'])

    if is_vol or is_kd:
        rank = 1 if (is_vol and is_kd) else (2 if is_vol else 3)
        return {
            "優劣": rank,
            "訊號": "🔥 帶量金叉" if rank == 1 else ("🚀 帶量攻擊" if rank == 2 else "🎯 低檔金叉"),
            "現價": round(curr['Close'], 2),
            "量比": round(curr['Volume']/curr['VMA20'], 2),
            "K值": int(curr['K']),
            "建議買進": round(curr['MA20'] * 1.005, 2),
            "波段賣出": round(curr['Close'] + (df['ATR'].iloc[-1] * 2.8), 2),
            "關鍵支撐": round(min(curr['MA20'], curr['Low']), 2)
        }
    return None

# --- 3. UI 介面與參數說明 ---
st.title("⚡ 2026 全台股 SOP 掃描")

# 增加動態調整說明
st.markdown("""
<div class="guide-box">
<b>💡 參數調整指南：</b><br>
1. <b>量能標準：</b> 數值愈低 (如 0.8)，掃出的股票愈多；數值愈高 (如 1.5)，篩選出的標的愈具爆發力。<br>
2. <b>KD 金叉門檻：</b> 設定 K 值在多少以下發生金叉才入榜。
   - <i>超跌反彈：</i> 建議設 20-30。
   - <i>中繼轉強：</i> 建議設 50-60。
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 動態參數設定")
    vol_target = st.slider("1. 量能標準 (倍數)", 0.5, 3.0, 1.0, 0.1)
    kd_limit = st.slider("2. KD 金叉門檻 (K值)", 20, 80, 50, 5)
    scan_limit = st.number_input("掃描檔數 (全掃設 2000)", 10, 2000, 2000)
    st.divider()
    if st.button("🔄 重置所有快取"): st.cache_data.clear()

# --- 4. 掃描執行 ---
if st.button("🔵 開始分析當前盤勢", use_container_width=True):
    all_stocks = get_full_taiwan_list()
    scan_items = list(all_stocks.items())[:scan_limit]
    
    results = []
    status = st.empty()
    bar = st.progress(0)
    start_t = time.time()

    # 批次獲取數據
    data = yf.download([s for s in scan_items], period="6mo", group_by='ticker', threads=True, progress=False)

    for idx, (sym, name) in enumerate(scan_items):
        processed = idx + 1
        pct = processed / len(scan_items)
        eta = int((time.time() - start_t) / processed * (len(scan_items) - processed)) if processed > 5 else 0
        
        status.markdown(f"**⏳ 掃描進度: {int(pct*100)}% | 剩餘時間: {eta} 秒**")
        bar.progress(pct)
        
        try:
            df = data[sym].dropna()
            res = analyze_sop_v3(df, vol_target, kd_limit)
            if res:
                res["股票"] = f"{sym.split('.')[0]} {name}"
                results.append(res)
        except: continue

    status.empty()
    bar.empty()

    if results:
        # 依優劣排序
        sorted_res = sorted(results, key=lambda x: x['優劣'])
        st.success(f"✅ 掃描完成！找到 {len(results)} 檔符合標的")
        
        for item in sorted_res:
            with st.container(border=True):
                st.write(f"### {item['股票']}")
                st.info(f"訊號狀態: {item['訊號']}")
                
                col1, col2 = st.columns(2)
                col1.metric("目前價格", f"{item['現價']}")
                col2.write(f"📊 量比：{item['量比']}x \n\n📈 K值：{item['K值']}")
                
                st.markdown(f"""
                <div class="price-box">
                🟢 建議買進：<span style="color:#00FF88;">{item['建議買進']}</span><br>
                🔴 波段賣出：<span style="color:#FF4B4B;">{item['波段賣出']}</span><br>
                🔵 關鍵支撐：<span style="color:#4FACFE;">{item['關鍵支撐']}</span>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.warning("⚠️ 依目前參數未找到標的。建議將【量能標準】調至 0.8 或將【KD 門檻】拉高。")

st.divider()
st.caption("⚠ 免責聲明：本工具僅供 2026 技術面研究，投資盈虧請自行負責並嚴格停損。")
