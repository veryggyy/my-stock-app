import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import os
import urllib3
from datetime import datetime

# 隱藏 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. 頁面設定 ---
st.set_page_config(page_title="2026 台股 SOP 終極掃描", layout="centered")

st.markdown("""
    <style>
    .block-container { padding-top: 1rem; max-width: 500px; }
    h3 { font-size: 1.8rem !important; font-weight: 800; color: #FFD700; margin-bottom: 5px; }
    [data-testid="stMetricValue"] { font-size: 2.2rem !important; color: #00FFCC !important; font-weight: 900; }
    .price-box { 
        font-size: 1.2rem; line-height: 2.2; font-weight: bold; padding: 15px; 
        background: #0f172a; border-radius: 12px; border: 1px solid #374151; 
    }
    .stProgress > div > div > div > div { background-color: #00ffcc; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 獲取全台股清單 ---
@st.cache_data(ttl=600)
def get_full_taiwan_list():
    stocks = {}
    file_path = "taiwan_stock_list.csv"
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()
                for line in lines:
                    parts = line.strip().split(',')
                    if len(parts) >= 2:
                        code = parts[0].strip().upper()
                        name = parts[1].strip()
                        if "代號" not in code and len(code) >= 4:
                            if not (code.endswith('.TW') or code.endswith('.TWO')):
                                code = f"{code}.TW"
                            stocks[code] = name
            if len(stocks) > 0: return stocks, f"✅ 已載入清單 (共 {len(stocks)} 檔)"
        except: pass
    return {"2330.TW": "台積電", "2317.TW": "鴻海"}, "⚠️ 讀取 CSV 失敗，使用保底清單"

# --- 3. 核心 SOP 分析引擎 (強勢起漲 + 跌深反彈) ---
def analyze_sop_v6(df, up_threshold):
    try:
        if df is None or len(df) < 45: return None
        df.columns = [str(c).capitalize() for c in df.columns]
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].apply(pd.to_numeric, errors='coerce').dropna()
        
        # 指標計算
        df['MA20'] = ta.sma(df['Close'], length=20)
        df['MA20_Slope'] = df['MA20'].diff(3) 
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        kd_df = ta.stoch(df['High'], df['Low'], df['Close'], k=14, d=3, smooth_k=3)
        df['K'], df['D'] = kd_df.iloc[:, 0], kd_df.iloc[:, 1]
        df['VMA5'] = ta.sma(df['Volume'], length=5)
        
        curr, prev = df.iloc[-1], df.iloc[-2]
        ret = (curr['Close'] / prev['Close'] - 1) * 100
        bias_20 = (curr['Close'] / curr['MA20'] - 1) * 100 # 月線乖離率
        
        # A. 強勢起漲邏輯
        is_trend = (curr['Close'] > curr['MA20']) and (curr['MA20_Slope'] > 0)
        is_kd_cross = (curr['K'] > curr['D']) and (prev['K'] <= prev['D'])
        is_breakout = (curr['Volume'] > curr['VMA5']) and (ret >= up_threshold)
        
        # B. 跌深反彈邏輯 (月線負乖離 > 10% 且 KD 低檔金叉)
        is_oversold = (bias_20 < -10.0) and (curr['K'] < 30) and (curr['K'] > curr['D']) and (prev['K'] <= prev['D'])

        if (is_trend and is_kd_cross and is_breakout) or is_oversold:
            mode = "🔥 三強共振 (起漲)" if not is_oversold else "💎 跌深反彈 (抄底)"
            atr_val = df['ATR'].iloc[-1]
            
            return {
                "訊號": mode,
                "現價": round(float(curr['Close']), 2),
                "漲幅": f"{round(ret, 2)}%",
                "量能比": f"{round(curr['Volume']/curr['VMA5'], 2)}x",
                "K值": int(curr['K']),
                "買進參考": round(float(curr['Close']), 2),
                "賣出參考": round(float(curr['Close'] + (atr_val * 2.5)), 2),
                "支撐參考": round(float(curr['Close'] - (atr_val * 1.5)), 2)
            }
    except: return None
    return None

# --- 4. 主介面 ---
st.title("⚡ 2026 台股 SOP 終極掃描")
st.caption(f"📅 系統日期: {datetime.now().strftime('%Y-%m-%d')}")

with st.sidebar:
    st.header("⚙️ 篩選參數")
    ret_target = st.slider("強勢股漲幅門檻 (%)", 0.5, 7.0, 2.0, 0.5)
    scan_limit = st.number_input("掃描數量", 10, 3000, 2800)
    if st.button("🔄 清除快取並重啟"):
        st.cache_data.clear()
        st.rerun()

# --- 5. 執行掃描 ---
if st.button("🔵 開始執行分析", use_container_width=True):
    all_stocks, status_msg = get_full_taiwan_list()
    st.info(status_msg)
    
    tickers = sorted(list(all_stocks.keys()))[:int(scan_limit)]
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    batch_size = 40 
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        status_text.text(f"掃描中: {i+1} ~ {min(i+batch_size, len(tickers))}...")
        try:
            data = yf.download(batch, period="6mo", group_by='ticker', auto_adjust=True, progress=False)
            for sym in batch:
                try:
                    df = data[sym].dropna() if len(batch) > 1 else data.dropna()
                    res = analyze_sop_v6(df, ret_target)
                    if res:
                        res["股票"] = f"{sym.split('.')[0]} {all_stocks[sym]}"
                        results.append(res)
                except: continue
        except: continue
        progress_bar.progress(min((i + batch_size) / len(tickers), 1.0))
    
    status_text.empty()
    progress_bar.empty()

    if results:
        st.success(f"✅ 找到 {len(results)} 檔符合標的")
        for item in results:
            with st.container(border=True):
                st.write(f"### {item['股票']}")
                st.write(f"**訊號：{item['訊號']}**")
                c1, c2 = st.columns(2)
                c1.metric("目前價格", f"{item['現價']}", f"{item['漲幅']}")
                c2.write(f"📊 量比: `{item['量能比']}` | 📈 K值: `{item['K值']}`")
                st.markdown(f"""
                <div class="price-box">
                🟢 建議買進：<span style="color:#00FF88;">{item['買進參考']}</span><br>
                🔵 關鍵支撐：<span style="color:#4FACFE;">{item['支撐參考']}</span><br>
                🔴 目標賣出：<span style="color:#FF4B4B;">{item['賣出參考']}</span>
                </div>
                """, unsafe_allow_html=True)
                st.caption("💡 註：建議買進價為當前參考；目標賣出與支撐位依 ATR 波動計算。")
    else:
        st.error("❌ 目前條件下無符合標的。")

st.divider()
st.caption("⚠ 免責聲明：本工具僅供參考，不構成投資建議。")
