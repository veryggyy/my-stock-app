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
    h3 { font-size: 2.2rem !important; font-weight: 800; color: #FFD700; margin-bottom: 5px; }
    [data-testid="stMetricValue"] { font-size: 3rem !important; color: #00FFCC !important; font-weight: 900; }
    .price-box { font-size: 1.5rem; line-height: 2.2; font-weight: bold; padding: 12px; background: #0f172a; border-radius: 10px; border: 1px solid #374151; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 獲取全台股清單 (修正版) ---
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
                    code = str(parts[0]).strip().upper()
                    name = str(parts[1]).strip()
                    if "代號" not in code and len(code) >= 4:
                        if not (code.endswith('.TW') or code.endswith('.TWO')):
                            code = f"{code}.TW"
                        stocks[code] = name
            if len(stocks) > 0: return stocks, "📡 已成功載入您的 CSV 股票清單"
    except: pass
    return {"2330.TW": "台積電", "2317.TW": "鴻海"}, "⚠️ 使用內建保底清單"

# --- 3. 核心 SOP 分析引擎 (修正數據讀取) ---
def analyze_sop_v4(df, vol_mult, kd_threshold):
    try:
        # 確保數據包含必要欄位且長度足夠
        if df is None or len(df) < 35: return None
        
        # 強制清理數據，確保沒有空值
        df = df.last('120D').copy() # 取最近 120 天數據
        df.columns = [c.capitalize() for c in df.columns] # 確保首字母大寫 (Open, High...)
        
        # 計算技術指標
        df['MA20'] = ta.sma(df['Close'], length=20)
        df['VMA20'] = ta.sma(df['Volume'], length=20)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        kd = ta.stoch(df['High'], df['Low'], df['Close'])
        df['K'], df['D'] = kd['STOCHk_14_3_3'], kd['STOCHd_14_3_3']
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 篩選條件：帶量 或 KD金叉
        is_vol = (curr['Volume'] > curr['VMA20'] * vol_mult)
        is_kd = (prev['K'] < kd_threshold) and (curr['K'] > curr['D'])

        if is_vol or is_kd:
            rank = 1 if (is_vol and is_kd) else (2 if is_vol else 3)
            return {
                "優劣": rank,
                "訊號": "🔥 帶量金叉" if rank == 1 else ("🚀 攻擊 (帶量)" if rank == 2 else "🎯 轉強 (金叉)"),
                "現價": round(float(curr['Close']), 2),
                "量比": round(float(curr['Volume'] / curr['VMA20']), 2),
                "K值": int(curr['K']),
                "建議買進": round(float(curr['MA20']), 2),
                "波段賣出": round(float(curr['Close'] + (df['ATR'].iloc[-1] * 2.2)), 2),
                "關鍵支撐": round(float(min(curr['MA20'], curr['Low'])), 2)
            }
    except:
        return None
    return None

# --- 4. 主介面 ---
st.title("⚡ 2026 全台股 SOP 掃描")
st.caption(f"📅 系統時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

with st.sidebar:
    st.header("⚙️ 參數設定")
    vol_target = st.slider("1. 量能倍數", 0.5, 3.0, 0.8, 0.1)
    kd_limit = st.slider("2. KD 門檻", 20, 85, 50, 5)
    scan_limit = st.number_input("3. 掃描檔數", 10, 2500, 500)
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

    # 分批下載優化
    batch_size = 40
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        status_text.text(f"正在掃描第 {i+1} ~ {min(i+batch_size, len(tickers))} 檔...")
        
        try:
            # 下載數據，確保處理 MultiIndex 問題
            data = yf.download(batch, period="6mo", group_by='ticker', auto_adjust=True, progress=False)
            
            for sym in batch:
                try:
                    # 根據下載數量提取 DataFrame
                    df = data[sym] if len(batch) > 1 else data
                    df = df.dropna()
                    if len(df) < 20: continue
                    
                    res = analyze_sop_v4(df, vol_target, kd_limit)
                    if res:
                        res["股票"] = f"{sym.split('.')[0]} {all_stocks[sym]}"
                        results.append(res)
                except: continue
        except: continue
        progress_bar.progress(min((i + batch_size) / len(tickers), 1.0))
    
    status_text.empty()
    progress_bar.empty()

    if results:
        st.success(f"✅ 掃描完成！找到 {len(results)} 檔符合標的")
        for item in sorted(results, key=lambda x: x['優劣']):
            with st.container(border=True):
                st.write(f"### {item['股票']}")
                st.info(f"訊號：{item['訊號']}")
                c1, c2 = st.columns(2)
                c1.metric("目前價格", f"{item['現價']}")
                c2.write(f"📊 量比：`{item['量比']}x` \n\n📈 K值：`{item['K值']}`")
                st.markdown(f'<div class="price-box">🟢 建議買進：<span style="color:#00FF88;">{item["建議買進"]}</span><br>🔴 波段賣出：<span style="color:#FF4B4B;">{item["波段賣出"]}</span><br>🔵 關鍵支撐：<span style="color:#4FACFE;">{item["關鍵支撐"]}</span></div>', unsafe_allow_html=True)
    else:
        st.error("❌ 目前條件下無符合標的。建議調低量能門檻(0.7)或增加掃描數量。")

st.divider()
st.caption("⚠ 免責聲明：僅供參考，投資盈虧自負。")
