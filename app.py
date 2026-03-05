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
st.set_page_config(page_title="2026 全台股 SOP 掃描器", layout="centered")

st.markdown("""
    <style>
    .block-container { padding-top: 1rem; max-width: 500px; }
    h3 { font-size: 1.8rem !important; font-weight: 800; color: #FFD700; margin-bottom: 5px; }
    [data-testid="stMetricValue"] { font-size: 2.2rem !important; color: #00FFCC !important; font-weight: 900; }
    .price-box { font-size: 1.2rem; line-height: 2; font-weight: bold; padding: 12px; background: #0f172a; border-radius: 10px; border: 1px solid #374151; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 獲取清單 ---
@st.cache_data(ttl=300)
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
            if len(stocks) > 0: return stocks, "已成功載入您的 CSV 股票清單"
    except: pass
    return {"2330.TW": "台積電", "2317.TW": "鴻海"}, "⚠️ 使用內建保底清單"

# --- 3. 核心 SOP 分析引擎 (強化結構解析) ---
def analyze_sop_v4(df, vol_mult, kd_threshold):
    try:
        if df is None or len(df) < 30: return None
        
        # 1. 統一欄位名稱並轉為浮點數
        df.columns = [str(c).capitalize() for c in df.columns]
        cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        df = df[cols].apply(pd.to_numeric, errors='coerce').dropna()
        
        # 2. 指標計算
        df['MA20'] = ta.sma(df['Close'], length=20)
        df['VMA20'] = ta.sma(df['Volume'], length=20)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        
        # 3. KD 計算 (處理 pandas_ta 可能的隨機欄位名)
        kd_df = ta.stoch(df['High'], df['Low'], df['Close'], k=14, d=3, smooth_k=3)
        k_val = kd_df.iloc[-1, 0] # 取最後一列的第一欄 (K)
        d_val = kd_df.iloc[-1, 1] # 取最後一列的第二欄 (D)
        prev_k = kd_df.iloc[-2, 0] # 前一天的 K
        
        curr_p = df['Close'].iloc[-1]
        curr_v = df['Volume'].iloc[-1]
        vma = df['VMA20'].iloc[-1]
        ma20 = df['MA20'].iloc[-1]
        
        # 4. 篩選邏輯 (寬鬆版)
        is_vol = (curr_v > vma * vol_mult)
        is_kd = (prev_k < kd_threshold) and (k_val > d_val)

        if is_vol or is_kd:
            rank = 1 if (is_vol and is_kd) else (2 if is_vol else 3)
            return {
                "優劣": rank,
                "訊號": "🔥 帶量金叉" if rank == 1 else ("🚀 攻擊 (帶量)" if rank == 2 else "🎯 轉強 (金叉)"),
                "現價": round(float(curr_p), 2),
                "量比": round(float(curr_v / vma), 2),
                "K值": int(k_val),
                "建議買進": round(float(ma20), 2),
                "波段賣出": round(float(curr_p + (df['ATR'].iloc[-1] * 2.1)), 2),
                "關鍵支撐": round(float(min(ma20, df['Low'].iloc[-1])), 2)
            }
    except: return None
    return None

# --- 4. 主介面 ---
st.title("⚡ 2026 全台股 SOP 掃描")
st.caption(f"📅 系統日期: {datetime.now().strftime('%Y-%m-%d')}")

with st.sidebar:
    st.header("⚙️ 參數設定")
    vol_target = st.slider("1. 量能倍數", 0.1, 2.0, 0.5, 0.1)
    kd_limit = st.slider("2. KD 門檻", 10, 90, 80, 5)
    scan_limit = st.number_input("3. 掃描檔數", 10, 2800, 300)
    if st.button("🔄 清除快取並重啟"):
        st.cache_data.clear()
        st.rerun()

# --- 5. 執行分析 ---
if st.button("🔵 開始分析符合標的", use_container_width=True):
    all_stocks, status_msg = get_full_taiwan_list()
    st.info(status_msg)
    
    tickers = sorted(list(all_stocks.keys()))[:int(scan_limit)]
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    # 分批下載：每次抓 20 檔，避免 MultiIndex 結構過於混亂
    batch_size = 20 
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        status_text.text(f"正在分析 {i+1} ~ {min(i+batch_size, len(tickers))} 檔...")
        try:
            # 獲取數據
            data = yf.download(batch, period="4mo", group_by='ticker', auto_adjust=True, progress=False)
            
            for sym in batch:
                try:
                    # 強制提取對應股票的數據
                    if len(batch) > 1:
                        df_target = data[sym].copy().dropna()
                    else:
                        df_target = data.copy().dropna()
                        
                    if len(df_target) < 25: continue
                    
                    res = analyze_sop_v4(df_target, vol_target, kd_limit)
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
        for item in sorted(results, key=lambda x: x['優劣']):
            with st.container(border=True):
                st.write(f"### {item['股票']}")
                st.info(f"訊號：{item['訊號']}")
                c1, c2 = st.columns(2)
                c1.metric("目前價格", f"{item['現價']}")
                c2.write(f"📊 量比：`{item['量比']}x` \n\n📈 K值：`{item['K值']}`")
                st.markdown(f'<div class="price-box">🟢 建議買進：{item["建議買進"]}<br>🔴 波段賣出：{item["波段賣出"]}<br>🔵 關鍵支撐：{item["關鍵支撐"]}</div>', unsafe_allow_html=True)
    else:
        st.error("❌ 目前條件下無符合標的。")

st.divider()
st.caption("⚠ 免責聲明：僅供參考，投資盈虧自負。")
