import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import urllib3
from datetime import datetime

# 隱藏 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. 頁面設定：手機優化佈局 ---
st.set_page_config(page_title="2026 三強共振 SOP 掃描", layout="centered")

st.markdown("""
    <style>
    .block-container { padding-top: 1rem; max-width: 500px; }
    h3 { font-size: 1.8rem !important; font-weight: 800; color: #FFD700; margin-bottom: 5px; }
    [data-testid="stMetricValue"] { font-size: 2.2rem !important; color: #00FFCC !important; font-weight: 900; }
    .price-box { 
        font-size: 1.2rem; line-height: 2; font-weight: bold; padding: 15px; 
        background: #0f172a; border-radius: 12px; border: 1px solid #3b82f6; 
    }
    .stProgress > div > div > div > div { background-color: #00ffcc; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 獲取全台股清單 (CSV 讀取邏輯) ---
@st.cache_data(ttl=600)
def get_full_taiwan_list():
    stocks = {}
    try:
        csv_url = "https://raw.githubusercontent.com"
        resp = requests.get(f"{csv_url}?v={datetime.now().timestamp()}", timeout=10)
        if resp.status_code == 200:
            lines = resp.text.strip().splitlines()
            for line in lines:
                parts = line.split(',')
                if len(parts) >= 2:
                    code = parts[0].strip().upper()
                    name = parts[1].strip()
                    if "代號" not in code and len(code) >= 4:
                        if not (code.endswith('.TW') or code.endswith('.TWO')):
                            code = f"{code}.TW"
                        stocks[code] = name
            if len(stocks) > 0: return stocks, f"📡 已成功載入 {len(stocks)} 檔股票清單"
    except: pass
    return {"2330.TW": "台積電", "2317.TW": "鴻海"}, "⚠️ CSV 讀取失敗，使用保底清單"

# --- 3. 核心 SOP 分析引擎 (三強共振版) ---
def analyze_sop_v5(df, up_threshold):
    try:
        if df is None or len(df) < 40: return None
        
        # 數據清洗
        df.columns = [str(c).capitalize() for c in df.columns]
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].apply(pd.to_numeric, errors='coerce').dropna()
        
        # 1. 趨勢指標：20MA 與 20MA 斜率
        df['MA20'] = ta.sma(df['Close'], length=20)
        df['MA20_Slope'] = df['MA20'].diff(3) # 近三日斜率
        
        # 2. 動能指標：KD 金叉 (14, 3, 3)
        kd_df = ta.stoch(df['High'], df['Low'], df['Close'], k=14, d=3, smooth_k=3)
        df['K'], df['D'] = kd_df.iloc[:, 0], kd_df.iloc[:, 1]
        
        # 3. 表態指標：5日均量
        df['VMA5'] = ta.sma(df['Volume'], length=5)
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # --- 判定邏輯 ---
        # A. 趨勢：價 > 20MA 且 20MA 斜率向上
        is_trend = (curr['Close'] > curr['MA20']) and (curr['MA20_Slope'] > 0)
        
        # B. 動能：KD 金叉 (今日 K > D 且 昨日 K <= D)
        is_kd_cross = (curr['K'] > curr['D']) and (prev['K'] <= prev['D'])
        
        # C. 表態：量 > 5日均量 且 今日漲幅 > 設定門檻
        ret = (curr['Close'] / prev['Close'] - 1) * 100
        is_breakout = (curr['Volume'] > curr['VMA5']) and (ret >= up_threshold)

        if is_trend and is_kd_cross and is_breakout:
            return {
                "訊號": "🔥 三強共振 (起漲訊號)",
                "現價": round(float(curr['Close']), 2),
                "漲幅": f"{round(ret, 2)}%",
                "量能比": f"{round(curr['Volume']/curr['VMA5'], 2)}x",
                "K值": int(curr['K']),
                "月線位置": round(float(curr['MA20']), 2)
            }
    except: return None
    return None

# --- 4. 主介面設計 ---
st.title("⚡ 2026 三強共振掃描")
st.caption(f"📅 系統日期: {datetime.now().strftime('%Y-%m-%d')}")

with st.sidebar:
    st.header("⚙️ 篩選門檻")
    ret_target = st.slider("今日漲幅門檻 (%)", 1.0, 7.0, 3.0, 0.5)
    scan_limit = st.number_input("掃描數量 (建議 1000 以上)", 10, 2800, 500)
    if st.button("🔄 清除快取並重啟"):
        st.cache_data.clear()
        st.rerun()

# --- 5. 執行分析 ---
if st.button("🔵 開始執行『三強共振』分析", use_container_width=True):
    all_stocks, status_msg = get_full_taiwan_list()
    st.info(status_msg)
    
    tickers = sorted(list(all_stocks.keys()))[:int(scan_limit)]
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    # 批次下載：每次 30 檔
    batch_size = 30 
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        status_text.text(f"正在分析 {i+1} ~ {min(i+batch_size, len(tickers))} 檔股票...")
        try:
            data = yf.download(batch, period="4mo", group_by='ticker', auto_adjust=True, progress=False)
            for sym in batch:
                try:
                    df_target = data[sym].dropna() if len(batch) > 1 else data.dropna()
                    if len(df_target) < 30: continue
                    
                    res = analyze_sop_v5(df_target, ret_target)
                    if res:
                        res["股票"] = f"{sym.split('.')[0]} {all_stocks[sym]}"
                        results.append(res)
                except: continue
        except: continue
        progress_bar.progress(min((i + batch_size) / len(tickers), 1.0))
    
    status_text.empty()
    progress_bar.empty()

    if results:
        st.success(f"✅ 找到 {len(results)} 檔符合『強勢起漲』標的")
        for item in results:
            with st.container(border=True):
                st.write(f"### {item['股票']}")
                st.write(f"**訊號：{item['訊號']}**")
                c1, c2 = st.columns(2)
                c1.metric("目前價格", f"{item['現價']}", f"{item['漲幅']}")
                c2.write(f"📊 量能比：`{item['量能比']}` \n\n📈 K值：`{item['K值']}`")
                st.markdown(f"""
                <div class="price-box">
                🟢 月線支撐：<span style="color:#00FF88;">{item['月線位置']}</span><br>
                🔵 趨勢方向：<span style="color:#4FACFE;">20MA 斜率向上 ↗</span>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.error("❌ 目前市場中查無符合標的。")
        st.info("💡 建議：調低『今日漲幅門檻』至 1.5% 或增加『掃描數量』。")

st.divider()
st.caption("⚠ 僅供參考。KD 金叉與帶量漲幅為強勢股常見特徵，投資應注意風險。")
