import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time
import requests
from datetime import datetime

# --- 1. 頁面設定：手機大字體與居中佈局 ---
st.set_page_config(page_title="2026 全台股 SOP 掃描", layout="centered")

st.markdown("""
    <style>
    /* 手機版窄螢幕居中優化 */
    .block-container { padding-top: 1rem; max-width: 500px; }
    
    /* 標題與大字體數據 */
    h3 { font-size: 2.2rem !important; font-weight: 800; color: #FFD700; margin-bottom: 5px; }
    [data-testid="stMetricValue"] { font-size: 3rem !important; color: #00FFCC !important; font-weight: 900; }
    
    /* 說明框樣式 */
    .guide-box {
        background-color: #1e293b;
        padding: 15px;
        border-radius: 12px;
        border-left: 6px solid #3b82f6;
        margin-bottom: 20px;
        font-size: 1.1rem;
    }
    
    /* 建議價格區塊 */
    .price-box {
        font-size: 1.5rem;
        line-height: 2.2;
        font-weight: bold;
        padding: 12px;
        background: #0f172a;
        border-radius: 10px;
        border: 1px solid #374151;
    }
    
    /* 進度條大字體 */
    .stProgress > div > div > div > div { background-color: #00ffcc; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 獲取全台股清單 (含上市與熱門上櫃) ---
@st.cache_data(ttl=86400)
def get_full_taiwan_list():
    stocks = {}
    try:
        # 上市公司 API
        res = requests.get('https://openapi.twse.com.tw').json()
        for s in res: stocks[f"{s['Code']}.TW"] = s['Name']
        # 熱門上櫃標的補充
        tpex = {"8069.TWO": "元太", "6488.TWO": "環球晶", "5274.TWO": "信驊", "3293.TWO": "鈊象", "6138.TWO": "茂達"}
        stocks.update(tpex)
    except:
        return {"2330.TW": "台積電", "2317.TW": "鴻海"}
    return stocks

# --- 3. 核心 SOP 分析引擎 ---
def analyze_sop_v4(df, vol_mult, kd_threshold):
    if df is None or len(df) < 60: return None
    
    # 計算技術指標
    df['MA20'] = ta.sma(df['Close'], length=20)
    df['MA60'] = ta.sma(df['Close'], length=60)
    df['VMA20'] = ta.sma(df['Volume'], length=20)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    macd = ta.macd(df['Close'])
    df['MACD_h'] = macd['MACDh_12_26_9']
    kd = ta.stoch(df['High'], df['Low'], df['Close'])
    df['K'], df['D'] = kd['STOCHk_14_3_3'], kd['STOCHd_14_3_3']

    curr, prev = df.iloc[-1], df.iloc[-2]

    # 門檻：站穩月線 (20MA)
    if not (curr['Close'] > curr['MA20']): return None

    # 訊號 A：帶量 (成交量 > 20日均量 * 倍數)
    is_vol = curr['Volume'] > curr['VMA20'] * vol_mult
    # 訊號 B：KD 金叉 (K值需低於動態設定門檻)
    is_kd = (prev['K'] < kd_threshold) and (curr['K'] > curr['D']) and (prev['K'] <= prev['D'])

    if is_vol or is_kd:
        rank = 1 if (is_vol and is_kd) else (2 if is_vol else 3)
        return {
            "優劣": rank,
            "訊號": "🔥 帶量金叉" if rank == 1 else ("🚀 攻擊 (帶量)" if rank == 2 else "🎯 轉強 (金叉)"),
            "現價": round(curr['Close'], 2),
            "量比": round(curr['Volume']/curr['VMA20'], 2),
            "K值": int(curr['K']),
            "建議買進": round(curr['MA20'] * 1.005, 2),
            "波段賣出": round(curr['Close'] + (df['ATR'].iloc[-1] * 2.8), 2),
            "關鍵支撐": round(min(curr['MA20'], curr['Low']), 2)
        }
    return None

# --- 4. 主介面設計 ---
st.title("⚡ 2026 全台股 SOP 掃描")
st.caption(f"📅 當前時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# 動態調整說明區
st.markdown("""
<div class="guide-box">
<b>⚙️ 參數調整秘訣：</b><br>
1. <b>量能標準：</b> 若標的太少，請調低至 <b>0.8</b> (溫和放量)；若要強勢股，調至 <b>1.2</b> 以上。<br>
2. <b>KD 門檻：</b> 設 <b>30</b> 找低檔反彈；設 <b>55</b> 找強勢中繼轉強。
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 掃描參數")
    vol_target = st.slider("1. 量能倍數門檻", 0.5, 3.0, 1.1, 0.1)
    kd_limit = st.slider("2. KD 金叉門檻 (K值)", 20, 80, 50, 5)
    scan_limit = st.number_input("3. 掃描檔數 (全掃設 2000)", 10, 2500, 2000)
    st.divider()
    if st.button("🔄 重置快取資料"):
        st.cache_data.clear()
        st.success("快取已清除")

# --- 5. 掃描執行邏輯 ---
if st.button("🔵 開始全自動分析", use_container_width=True):
    all_stocks = get_full_taiwan_list()
    # 提取 (代號, 名稱) 元組清單
    scan_items = list(all_stocks.items())[:scan_limit]
    # 提取純代號清單供 yfinance 使用 (修正 TypeError 關鍵)
    tickers = [item[0] for item in scan_items]
    
    results = []
    status_msg = st.empty()
    progress_bar = st.progress(0)
    start_time = time.time()

    # 批次下載
    with st.spinner('連線 Yahoo Finance 獲取大數據...'):
        data = yf.download(tickers, period="6mo", group_by='ticker', threads=True, progress=False)

    for idx, (sym, name) in enumerate(scan_items):
        # 計算進度
        processed = idx + 1
        pct = processed / len(scan_items)
        elapsed = time.time() - start_time
        eta = int((elapsed / processed) * (len(scan_items) - processed)) if processed > 5 else 0
        
        status_msg.markdown(f"### ⏳ 進度: {int(pct*100)}% | 剩餘: {eta}秒")
        progress_bar.progress(pct)
        
        try:
            # 取得單一股票數據
            if len(tickers) > 1:
                df = data[sym].dropna()
            else:
                df = data.dropna()
                
            res = analyze_sop_v4(df, vol_target, kd_limit)
            if res:
                res["股票"] = f"{sym.split('.')[0]} {name}"
                results.append(res)
        except:
            continue

    status_msg.empty()
    progress_bar.empty()

    # --- 6. 結果呈現 (手機優化) ---
    if results:
        # 按優劣排序 (1=最優)
        sorted_res = sorted(results, key=lambda x: x['優劣'])
        st.success(f"✅ 掃描完成！符合條件標的：{len(results)} 檔")
        
        for item in sorted_res:
            with st.container(border=True):
                st.write(f"### {item['股票']}")
                st.info(f"訊號：{item['訊號']}")
                
                c1, c2 = st.columns(2)
                c1.metric("目前價格", f"{item['現價']}")
                c2.write(f"📊 量比：`{item['量比']}x` \n\n📈 K值：`{item['K值']}`")
                
                st.markdown(f"""
                <div class="price-box">
                🟢 建議買進：<span style="color:#00FF88;">{item['建議買進']}</span><br>
                🔴 波段賣出：<span style="color:#FF4B4B;">{item['波段賣出']}</span><br>
                🔵 關鍵支撐：<span style="color:#4FACFE;">{item['關鍵支撐']}</span>
                </div>
                """, unsafe_allow_html=True)
                st.write(f"🛡️ 建議停損：`{round(item['現價']*0.95, 1)}` (5%)")
    else:
        st.warning("⚠️ 依目前參數未找到標的。請嘗試調低【量能標準】至 0.8 或調高【KD 門檻】。")

st.divider()
st.caption("⚠ 免責聲明：本工具僅供 2026 技術分析參考。投資盈虧請自行負責。")
