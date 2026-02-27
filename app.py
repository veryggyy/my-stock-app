import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime

# --- 1. 頁面與手機版大字體 CSS 設定 ---
st.set_page_config(page_title="2026 SOP 掃描器", layout="centered") # 手機建議 centered

st.markdown("""
    <style>
    /* 全域字體放大 */
    html, body, [class*="css"] { font-size: 1.1rem; }
    h1 { font-size: 2.2rem !important; }
    h3 { font-size: 1.8rem !important; color: #FFD700; } /* 股票名稱 */
    
    /* 讓 Metric (價格) 更醒目 */
    [data-testid="stMetricValue"] { font-size: 2.5rem !important; font-weight: 700; }
    
    /* 強化卡片視覺 */
    div[data-testid="stVerticalBlock"] > div[style*="border"] {
        border: 2px solid #4B5563 !important;
        border-radius: 15px !important;
        padding: 20px !important;
        background-color: #1F2937 !important;
        margin-bottom: 15px !important;
    }
    
    /* 進度條顏色 */
    .stProgress > div > div > div > div { background-image: linear-gradient(to right, #4facfe 0%, #00f2fe 100%); }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_stock_list():
    # 內建 2026 關鍵權值與 AI 供應鏈
    return {
        "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", 
        "2308.TW": "台達電", "2382.TW": "廣達", "3231.TW": "緯創",
        "2357.TW": "華碩", "3711.TW": "日月光", "2603.TW": "長榮",
        "2881.TW": "富邦金", "2882.TW": "國泰金", "2408.TW": "南亞科"
    }

# --- 2. 核心分析引擎 (加入優先級邏輯) ---
def analyze_2026_sop(df, vol_mult):
    if df is None or len(df) < 60: return None
    
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

    # 基本門檻：站穩月線與季線
    is_bullish = curr['Close'] > curr['MA20'] and curr['Close'] > curr['MA60']
    if not is_bullish: return None

    # 訊號 A：帶量攻擊 (優先權最高)
    is_breakout = (curr['Volume'] > curr['VMA20'] * vol_mult) and (curr['MACD_h'] > prev['MACD_h'])
    
    # 訊號 B：KD 金叉 (優先權次之)
    is_kd_cross = (prev['K'] < 40) and (curr['K'] > curr['D']) and (prev['K'] <= prev['D'])

    if is_breakout or is_kd_cross:
        # 計算權重：1 為最優 (帶量且金叉), 2 為帶量, 3 為單純金叉
        rank = 1 if (is_breakout and is_kd_cross) else (2 if is_breakout else 3)
        return {
            "優劣": rank,
            "標籤": "🔥 極強訊號" if rank == 1 else ("🚀 帶量攻擊" if rank == 2 else "🎯 回測金叉"),
            "現價": round(curr['Close'], 2),
            "漲跌": round(curr['Close'] - prev['Close'], 2),
            "量比": round(curr['Volume']/curr['VMA20'], 1),
            "KD": int(curr['K']),
            "支撐": round(curr['MA20'], 1)
        }
    return None

# --- 3. 手機版 UI ---
st.title("⚡ 2026 SOP 掃描")
st.write(f"📅 {datetime.now().strftime('%m/%d %H:%M')} | 直式操作模式")

stock_dict = get_stock_list()
symbols = list(stock_dict.keys())

with st.expander("🛠️ 參數調整 (手機點選)"):
    vol_target = st.slider("成交量門檻", 0.5, 2.5, 1.0, 0.1)
    if st.button("🔄 重置快取"): st.cache_data.clear()

if st.button("🚀 開始掃描全台股", use_container_width=True):
    results = []
    msg_box = st.empty()
    bar_box = st.empty()
    start_time = time.time()
    
    data = yf.download(symbols, period="6mo", group_by='ticker', threads=True, progress=False)
    
    total = len(symbols)
    for idx, (sym, name) in enumerate(stock_dict.items()):
        pct = int(((idx+1)/total)*100)
        eta = int(((time.time()-start_time)/(idx+1))*(total-(idx+1))) if idx > 0 else 0
        
        msg_box.markdown(f"### ⏳ 進度: {pct}% \n**預計剩餘: {eta} 秒**")
        bar_box.progress((idx+1)/total)
        
        try:
            df = data[sym].dropna()
            res = analyze_2026_sop(df, vol_target)
            if res:
                res["股票"] = f"{sym.split('.')[0]} {name}"
                results.append(res)
        except: continue

    msg_box.empty()
    bar_box.empty()

    # --- 4. 結果呈現 (依優劣排序) ---
    if results:
        # 按 '優劣' 排序 (數字越小越前面)
        sorted_res = sorted(results, key=lambda x: x['優劣'])
        
        st.success(f"找到 {len(sorted_res)} 檔優質標的")
        
        for item in sorted_res:
            with st.container(border=True):
                # 標題與訊號標籤
                st.markdown(f"### {item['股票']}")
                if item['優劣'] == 1:
                    st.error(f"【{item['標籤']}】優先關注") # 用紅色強調
                else:
                    st.info(f"【{item['標籤']}】")
                
                # 價格大數字
                st.metric("目前股價", f"{item['現價']} 元", f"{item['漲跌']} 元")
                
                # 詳細數據 (直式清單)
                st.write(f"📊 **量能倍數：** `{item['量比']}x`")
                st.write(f"📈 **K 值水準：** `{item['KD']}`")
                st.write(f"🛡️ **支撐(月線)：** `{item['支撐']}`")
                st.write(f"🛡️ **建議停損：** `{round(item['現價']*0.95, 1)}` (5%)")
    else:
        st.warning("當前暫無符合 SOP 標的，請降低量能門檻再試。")

st.divider()
st.caption("⚠ 技術分析僅供參考，2026 投資請嚴格執行停損。")
