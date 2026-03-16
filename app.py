import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import os
import requests
from datetime import datetime
from collections import Counter

# --- 1. 頁面設定 ---
st.set_page_config(page_title="2026 台股趨勢共振系統", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background: #1e293b; padding: 15px; border-radius: 10px; border-left: 5px solid #00ffcc; }
    .industry-tag { background: #334155; color: #cbd5e1; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; }
    .price-box { 
        font-size: 1.1rem; line-height: 1.8; font-weight: bold; padding: 20px; 
        background: #0f172a; border-radius: 12px; border: 1px solid #1e293b; 
    }
    h3 { color: #00ffcc !important; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 資料獲取與產業分類 (對應圖片：產業是否集中) ---
@st.cache_data(ttl=3600)
def get_taiwan_stock_data():
    """獲取台股清單並標註產業類別"""
    # 這裡建議準備一份包含代號、名稱、產業的 CSV
    # 範例暫用模擬資料，實務上可從證交所 API 或公開資訊觀測站抓取
    stocks = {}
    industries = {}
    file_path = "taiwan_stock_list.csv"
    
    if os.path.exists(file_path):
        df_list = pd.read_csv(file_path)
        for _, row in df_list.iterrows():
            code = str(row['代號']).strip()
            suffix = ".TW" if len(code) == 4 else ".TWO" # 簡單判斷上市櫃
            full_code = f"{code}{suffix}"
            stocks[full_code] = row['名稱']
            industries[full_code] = row.get('產業', '其他')
    else:
        # 預設範例
        stocks = {"2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2382.TW": "廣達", "3231.TW": "緯創"}
        industries = {"2330.TW": "半導體", "2317.TW": "其他電子", "2454.TW": "半導體", "2382.TW": "電腦週邊", "3231.TW": "電腦週邊"}
        
    return stocks, industries

# --- 3. 核心 SOP 分析引擎 (對應圖片：趨勢是否成立) ---
def analyze_trend_sop(df, ticker, name, industry, up_threshold):
    try:
        if len(df) < 65: return None
        
        # 指標計算
        df['MA20'] = ta.sma(df['Close'], length=20)
        df['MA60'] = ta.sma(df['Close'], length=60)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        kd = ta.stoch(df['High'], df['Low'], df['Close'], k=9, d=3)
        df['K'], df['D'] = kd.iloc[:, 0], kd.iloc[:, 1]
        df['VMA5'] = ta.sma(df['Volume'], length=5)
        
        curr, prev = df.iloc[-1], df.iloc[-2]
        
        # --- 策略過濾邏輯 ---
        # 1. 趨勢成立：多頭排列 (價格 > MA20 > MA60)
        is_bull = curr['Close'] > curr['MA20'] > curr['MA60']
        # 2. 資金流向：今日量能 > 5日均量 1.2倍 且 漲幅達標
        ret = (curr['Close'] / prev['Close'] - 1) * 100
        vol_ratio = curr['Volume'] / curr['VMA5']
        is_money_flow = (vol_ratio > 1.2) and (ret >= up_threshold)
        # 3. 動能轉強：KD金叉
        is_kd_cross = (curr['K'] > curr['D']) and (prev['K'] <= prev['D'])
        
        if is_bull and is_money_flow and is_kd_cross:
            score = ret * 0.4 + vol_ratio * 0.6 # 綜合權重評分
            return {
                "股票": f"{ticker.split('.')[0]} {name}",
                "產業": industry,
                "現價": round(float(curr['Close']), 2),
                "漲幅": round(ret, 2),
                "量比": round(vol_ratio, 2),
                "目標": round(float(curr['Close'] + (curr['ATR'] * 2)), 2),
                "支撐": round(float(curr['MA20']), 2), # 以月線為關鍵支撐
                "評分": score
            }
    except: return None
    return None

# --- 4. 主介面 UI ---
st.title("⚡ 2026 台股三位一體掃描器")
st.markdown("🎯 策略邏輯：**資金流向** (量增) + **產業群聚** (自動統計) + **趨勢成立** (MA/KD共振)")

with st.sidebar:
    st.header("🔍 篩選條件")
    up_target = st.slider("突破漲幅 (%)", 0.0, 7.0, 2.0)
    scan_count = st.number_input("掃描檔數", 100, 2000, 500)
    st.divider()
    st.info("💡 建議收盤後執行，確認資金流向最準確。")

if st.button("🚀 開始掃描全市場強勢股", use_container_width=True):
    stocks, industries = get_taiwan_stock_data()
    tickers = list(stocks.keys())[:scan_count]
    
    results = []
    progress = st.progress(0)
    
    # 批次下載數據
    data = yf.download(tickers, period="6mo", group_by='ticker', progress=False)
    
    for i, ticker in enumerate(tickers):
        try:
            df = data[ticker].dropna() if len(tickers) > 1 else data.dropna()
            res = analyze_trend_sop(df, ticker, stocks[ticker], industries[ticker], up_target)
            if res:
                results.append(res)
        except: continue
        progress.progress((i + 1) / len(tickers))

    if results:
        # --- 5. 數據呈現與產業統計 (對應圖片：產業是否集中) ---
        df_res = pd.DataFrame(results).sort_values(by="評分", ascending=False)
        
        # 產業集中度分析
        ind_counts = Counter([r['產業'] for r in results])
        top_industry = ind_counts.most_common(3)
        
        st.subheader("📊 當前資金集中產業")
        cols = st.columns(len(top_industry))
        for idx, (ind, count) in enumerate(top_industry):
            cols[idx].metric(f"Top {idx+1} {ind}", f"{count} 檔", "符合趨勢成立")

        st.divider()

        # 顯示個股明細
        st.subheader(f"🔥 符合 SOP 標的 (共 {len(results)} 檔)")
        for _, item in df_res.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 1, 2])
                with c1:
                    st.markdown(f"### {item['股票']}")
                    st.markdown(f"<span class='industry-tag'>{item['產業']}</span>", unsafe_allow_html=True)
                with c2:
                    st.metric("現價", f"{item['現價']}", f"{item['漲幅']}%")
                with c3:
                    st.markdown(f"""
                    <div class="price-box">
                    🎯 目標價：<span style="color:#FF4B4B;">{item['目標']}</span><br>
                    🛡️ 月線支撐：<span style="color:#4FACFE;">{item['支撐']}</span><br>
                    📈 量能增幅：{item['量比']}x
                    </div>
                    """, unsafe_allow_html=True)
    else:
        st.warning("⚠️ 目前市場尚未掃描到符合『三強共振』的標的，請降低漲幅門檻再試。")

st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')} | 投資有風險，操作請設停損。")
