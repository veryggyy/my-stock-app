import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time
import requests
from datetime import datetime

# --- 1. 頁面與手機大字體設定 ---
st.set_page_config(page_title="2026 SOP 全球掃描", layout="centered")

st.markdown("""
    <style>
    html, body { font-size: 1.1rem; }
    h3 { font-size: 1.8rem !important; color: #FFD700; margin-bottom: 5px; }
    [data-testid="stMetricValue"] { font-size: 2.2rem !important; font-weight: 800; color: #00ffcc; }
    .stProgress > div > div > div > div { background-color: #00ffcc; }
    div[data-testid="stVerticalBlock"] > div[style*="border"] {
        border: 2px solid #374151 !important;
        border-radius: 12px !important;
        padding: 15px !important;
        background-color: #111827 !important;
    }
    .price-tag { font-size: 1.2rem; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 自動獲取全台股清單 (API) ---
@st.cache_data(ttl=86400)
def get_all_taiwan_stocks():
    stocks = {}
    try:
        # 上市公司清單
        res = requests.get('https://openapi.twse.com.tw')
        for item in res.json():
            stocks[f"{item['Code']}.TW"] = item['Name']
        # 上櫃公司清單 (簡易示意, 實務上可串接 TPEx)
        stocks.update({"8069.TWO": "元太", "6488.TWO": "環球晶", "5274.TWO": "信驊"})
    except:
        return {"2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科"}
    return stocks

# --- 3. 分析引擎 (含價格建議邏輯) ---
def analyze_sop_v2(df, vol_mult):
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

    # 1. 趨勢過濾
    if not (curr['Close'] > curr['MA20'] > curr['MA60']): return None

    # 2. 訊號判定
    is_vol = curr['Volume'] > curr['VMA20'] * vol_mult
    is_macd = curr['MACD_h'] > prev['MACD_h']
    is_kd = (prev['K'] < 40) and (curr['K'] > curr['D'])

    if (is_vol and is_macd) or is_kd:
        rank = 1 if (is_vol and is_kd) else (2 if is_vol else 3)
        
        # 價格建議邏輯
        support = round(curr['MA20'], 2)
        buy_price = round(curr['MA20'] * 1.01, 2) # 月線上方 1%
        sell_price = round(curr['Close'] + (curr['ATR'] * 2.5), 2) # ATR 擴張賣點
        
        return {
            "優劣": rank,
            "標籤": "🔥 特優 (帶量金叉)" if rank == 1 else ("🚀 攻擊 (帶量)" if rank == 2 else "🎯 轉強 (金叉)"),
            "現價": round(curr['Close'], 2),
            "買進": buy_price,
            "賣出": sell_price,
            "支撐": support,
            "量比": round(curr['Volume']/curr['VMA20'], 1)
        }
    return None

# --- 4. 主介面 ---
st.title("⚡ 2026 全台股 SOP 掃描")
st.caption(f"當前模式：手機直式大字體 | 2026-02-27")

all_stocks = get_all_taiwan_stocks()
with st.sidebar:
    st.header("⚙️ 設定")
    vol_target = st.slider("量能門檻", 0.5, 3.0, 1.1)
    batch_size = st.number_input("掃描標的數 (預設全掃)", 10, 2000, 100)

if st.button("🔍 開始全自動掃描", use_container_width=True):
    results = []
    progress_info = st.empty()
    bar = st.progress(0)
    start_time = time.time()
    
    # 限制數量以防 API 封鎖
    scan_list = list(all_stocks.items())[:batch_size]
    symbols = [s[0] for s in scan_list]
    
    data = yf.download(symbols, period="6mo", group_by='ticker', threads=True, progress=False)
    
    for idx, (sym, name) in enumerate(scan_list):
        # 進度與時間計算
        processed = idx + 1
        pct = int((processed / len(scan_list)) * 100)
        elapsed = time.time() - start_time
        eta = int((elapsed / processed) * (len(scan_list) - processed))
        
        progress_info.markdown(f"### ⏳ 進度: {pct}% \n預計剩餘: `{eta}` 秒")
        bar.progress(processed / len(scan_list))
        
        try:
            df = data[sym].dropna()
            res = analyze_sop_v2(df, vol_target)
            if res:
                res["股票"] = f"{sym.split('.')[0]} {name}"
                results.append(res)
        except: continue

    progress_info.empty()
    bar.empty()

    if results:
        # 按優劣排序 (1 > 2 > 3)
        sorted_res = sorted(results, key=lambda x: x['優劣'])
        st.success(f"✅ 掃描完成！找到 {len(results)} 檔符合標的")
        
        for item in sorted_res:
            with st.container(border=True):
                st.markdown(f"### {item['股票']}")
                st.info(f"**訊號：{item['標籤']}**")
                
                c1, c2 = st.columns(2)
                c1.metric("目前價", f"{item['現價']}")
                c2.write(f"📊 量比：`{item['量比']}x`")
                
                st.markdown("---")
                # 建議價格區 (大字體強化)
                st.markdown(f"🟢 **建議買進：** <span class='price-tag' style='color:#00ff88;'>{item['買進']}</span>", unsafe_allow_html=True)
                st.markdown(f"🔴 **波段賣出：** <span class='price-tag' style='color:#ff4b4b;'>{item['賣出']}</span>", unsafe_allow_html=True)
                st.markdown(f"🔵 **關鍵支撐：** <span class='price-tag' style='color:#4facfe;'>{item['支撐']}</span>", unsafe_allow_html=True)
    else:
        st.warning("⚠️ 查無符合標的。")

st.caption("⚠ 免責聲明：技術分析僅供參考，2026 操作務必嚴格執行止損。")
