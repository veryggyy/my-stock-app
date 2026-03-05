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

# --- 2. 獲取全台股清單 ---
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

# --- 3. 核心 SOP 分析引擎 (強化容錯) ---
def analyze_sop_v4(df, vol_mult, kd_threshold):
    try:
        if df is None or len(df) < 30: return None
        
        # 統一欄位名稱並轉為浮點數
        df.columns = [c.capitalize() for c in df.columns]
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].apply(pd.to_numeric, errors='coerce').dropna()
        
        # 計算技術指標
        df['MA20'] = ta.sma(df['Close'], length=20)
        df['VMA20'] = ta.sma(df['Volume'], length=20)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        
        # 計算 KD
        kd = ta.stoch(df['High'], df['Low'], df['Close'])
        df['K'] = kd['STOCHk_14_3_3']
        df['D'] = kd['STOCHd_14_3_3']
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 核心邏輯：放寬門檻 (只要滿足其一)
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
    except: return None
    return None

# --- 4. 主介面 ---
st.title("⚡ 2026 全台股 SOP 掃描")
st.caption(f"📅 當前時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

with st.sidebar:
    st.header("⚙️ 參數設定")
    vol_target = st.slider("1. 量能倍數", 0.3, 3.0, 0.7, 0.1) # 下限調低至 0.3
    kd_limit = st.slider("2. KD 門檻", 10, 90, 60, 5) # 範圍放寬
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

    # 批次下載優化 (減少每批數量，提高穩定性)
    batch_size = 20 
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        status_text.text(f"正在掃描第 {i+1} 檔以後的股票...")
        
        try:
            # 獲取數據
            data = yf.download(batch, period="4mo", group_by='ticker', auto_adjust=True, progress=False)
            
            for sym in batch:
                try:
                    # 處理單檔與多檔下載的結構差異
                    if len(batch) > 1:
                        if sym not in data.columns.levels[0]: continue
                        df = data[sym].dropna()
                    else:
                        df = data.dropna()
                        
                    if len(df) < 25: continue
                    
                    res = analyze_sop_v4(df, vol_target, kd_limit)
                    if res:
                        res["股票"] = f"{sym.replace('.TW','').replace('.TWO','')} {all_stocks[sym]}"
                        results.append(res)
                except: continue
        except: continue
        progress_bar.progress(min((i + batch_size) / len(tickers), 1.0))
    
    status_text.empty()
    progress_bar.empty()

    if results:
        st.success(f"✅ 掃描完成！找到 {len(results)} 檔符合標的")
        # 按訊號優劣排序
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
        st.info("💡 提示：請試著調低『量能倍數』或提高『KD 門檻』再試一次。")

st.divider()
st.caption("⚠ 免責聲明：本工具僅供參考，投資盈虧請自行負責。")
