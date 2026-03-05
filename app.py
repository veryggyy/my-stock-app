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
    .block-container { padding-top: 1rem; max-width: 500px; }
    h3 { font-size: 2.2rem !important; font-weight: 800; color: #FFD700; margin-bottom: 5px; }
    [data-testid="stMetricValue"] { font-size: 3rem !important; color: #00FFCC !important; font-weight: 900; }
    .guide-box {
        background-color: #1e293b;
        padding: 15px;
        border-radius: 12px;
        border-left: 6px solid #3b82f6;
        margin-bottom: 20px;
        font-size: 1.1rem;
    }
    .price-box {
        font-size: 1.5rem;
        line-height: 2.2;
        font-weight: bold;
        padding: 12px;
        background: #0f172a;
        border-radius: 10px;
        border: 1px solid #374151;
    }
    .stProgress > div > div > div > div { background-color: #00ffcc; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 獲取全台股清單 (加入斷線偵測) ---
@st.cache_data(ttl=86400)
def get_full_taiwan_list():
    stocks = {}
    try:
        # 嘗試從證交所 OpenAPI 獲取清單
        response = requests.get('https://openapi.twse.com.tw', timeout=10)
        if response.status_code == 200:
            res = response.json()
            for s in res:
                stocks[f"{s['Code']}.TW"] = s['Name']
            # 加入常用上櫃標的
            tpex = {"8069.TWO": "元太", "6488.TWO": "環球晶", "5274.TWO": "信驊", "3293.TWO": "鈊象", "6138.TWO": "茂達"}
            stocks.update(tpex)
        else:
            return None # 回傳 None 代表連線失敗
    except:
        return None # 發生任何錯誤皆視為連線失敗
    return stocks

# --- 3. 核心 SOP 分析引擎 ---
def analyze_sop_v4(df, vol_mult, kd_threshold):
    if df is None or len(df) < 40: return None
    
    # 計算技術指標
    df['MA20'] = ta.sma(df['Close'], length=20)
    df['VMA20'] = ta.sma(df['Volume'], length=20)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    kd = ta.stoch(df['High'], df['Low'], df['Close'])
    df['K'], df['D'] = kd['STOCHk_14_3_3'], kd['STOCHd_14_3_3']

    curr, prev = df.iloc[-1], df.iloc[-2]

    # 篩選邏輯
    is_trend_ok = curr['Close'] > (curr['MA20'] * 0.98)
    if not is_trend_ok: return None

    is_vol = (curr['Volume'] > curr['VMA20'] * vol_mult) or (curr['Close'] > curr['Open'] and curr['Volume'] > curr['VMA20'] * 0.9)
    is_kd = (prev['K'] < kd_threshold) and (curr['K'] > curr['D'])

    if is_vol or is_kd:
        rank = 1 if (is_vol and is_kd) else (2 if is_vol else 3)
        return {
            "優劣": rank,
            "訊號": "🔥 帶量金叉" if rank == 1 else ("🚀 攻擊 (帶量)" if rank == 2 else "🎯 轉強 (金叉)"),
            "現價": round(curr['Close'], 2),
            "量比": round(curr['Volume'] / curr['VMA20'], 2),
            "K值": int(curr['K']),
            "建議買進": round(curr['MA20'], 2),
            "波段賣出": round(curr['Close'] + (df['ATR'].iloc[-1] * 2.5), 2),
            "關鍵支撐": round(min(curr['MA20'], curr['Low']), 2)
        }
    return None

# --- 4. 主介面設計 ---
st.title("⚡ 2026 全台股 SOP 掃描")
st.caption(f"📅 掃描時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

st.markdown("""
<div class="guide-box">
<b>⚙️ 參數調整秘訣：</b><br>
1. <b>量能標準：</b> 若標的太少，請調低至 <b>0.7</b>。<br>
2. <b>KD 門檻：</b> 設 <b>30</b> 找超跌；設 <b>60</b> 找強勢。
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 掃描參數")
    vol_target = st.slider("1. 量能倍數門檻", 0.5, 3.0, 1.0, 0.1)
    kd_limit = st.slider("2. KD 金叉門檻 (K值)", 20, 85, 55, 5)
    scan_limit = st.number_input("3. 掃描檔數", 10, 2500, 1000)
    if st.button("🔄 重置快取資料"):
        st.cache_data.clear()
        st.success("快取已清除")

# --- 5. 執行邏輯 ---
if st.button("🔵 開始分析符合標的", use_container_width=True):
    all_stocks = get_full_taiwan_list()
    
    if all_stocks is None:
        st.error("❌ 網路連線失敗：無法取得證交所股票清單")
        st.info("💡 請確認您的網路連線，或檢查證交所 API 是否正常運作。")
    else:
        scan_items = list(all_stocks.items())[:scan_limit]
        tickers = [item[0] for item in scan_items]
        
        results = []
        progress_bar = st.progress(0)

        with st.spinner('獲取市場數據中...'):
            data = yf.download(tickers, period="4mo", group_by='ticker', threads=True, progress=False)

        for idx, (sym, name) in enumerate(scan_items):
            progress_bar.progress((idx + 1) / len(scan_items))
            try:
                # 處理單檔與多檔數據結構差異
                df = data[sym].dropna() if len(tickers) > 1 else data.dropna()
                if df.empty: continue
                res = analyze_sop_v4(df, vol_target, kd_limit)
                if res:
                    res["股票"] = f"{sym.split('.')[0]} {name}"
                    results.append(res)
            except:
                continue

        progress_bar.empty()

        if results:
            sorted_res = sorted(results, key=lambda x: x['優劣'])
            st.success(f"✅ 掃描完成！符合條件：{len(results)} 檔")
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
        else:
            st.error("❌ 今日查無符合標的")
            st.info("💡 建議操作：請嘗試調低量能門檻或增加掃描檔數。")

st.divider()
st.caption("⚠ 免責聲明：本工具僅供 2026 技術分析參考。投資盈虧請自行負責。")
