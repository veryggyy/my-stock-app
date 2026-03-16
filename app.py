import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import os
from datetime import datetime
from collections import Counter

# --- 1. 頁面風格設定 ---
st.set_page_config(page_title="2026 台股三位一體系統", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background: #1e293b; padding: 15px; border-radius: 10px; border-left: 5px solid #00ffcc; }
    .industry-tag { background: #334155; color: #00ffcc; padding: 3px 10px; border-radius: 20px; font-size: 0.85rem; font-weight: bold; }
    .price-box { 
        font-size: 1.1rem; line-height: 1.8; font-weight: bold; padding: 20px; 
        background: #0f172a; border-radius: 12px; border: 1px solid #334155; 
    }
    h3 { color: #ffffff !important; margin-bottom: 0px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 產業資料準備 (對應圖片：產業是否集中) ---
@st.cache_data
def load_stock_info():
    """自動建立產業清單，若有 CSV 則讀取，沒有則使用內建預設"""
    file_path = "taiwan_stock_list.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        # 預期 CSV 格式: 代號, 名稱, 產業
        info = {f"{str(row['代號']).strip()}.TW": {"name": row['名稱'], "ind": row['產業']} for _, row in df.iterrows()}
        return info
    else:
        # 內建核心權值股範例 (建議後續補充 CSV)
        return {
            "2330.TW": {"name": "台積電", "ind": "半導體"},
            "2317.TW": {"name": "鴻海", "ind": "組裝代工"},
            "2454.TW": {"name": "聯發科", "ind": "半導體"},
            "2382.TW": {"name": "廣達", "ind": "AI伺服器"},
            "3231.TW": {"name": "緯創", "ind": "AI伺服器"},
            "2308.TW": {"name": "台達電", "ind": "電源供應"},
            "2603.TW": {"name": "長榮", "ind": "航運"},
            "1513.TW": {"name": "中興電", "ind": "重電"},
            "1519.TW": {"name": "華城", "ind": "重電"},
        }

# --- 3. 核心 SOP 分析 (對應圖片：趨勢是否成立/資金流向) ---
def analyze_sop(df, ticker, info, up_threshold):
    try:
        if len(df) < 60: return None
        
        # 指標計算
        df['MA20'] = ta.sma(df['Close'], length=20)
        df['MA60'] = ta.sma(df['Close'], length=60)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        kd = ta.stoch(df['High'], df['Low'], df['Close'], k=9, d=3)
        df['K'], df['D'] = kd.iloc[:, 0], kd.iloc[:, 1]
        df['VMA5'] = ta.sma(df['Volume'], length=5)
        
        curr, prev = df.iloc[-1], df.iloc[-2]
        
        # 1. 趨勢成立：多頭排列 (價格 > MA20 > MA60)
        is_bull = curr['Close'] > curr['MA20'] > curr['MA60']
        
        # 2. 資金流向：量比 > 1.2 且 漲幅 > 門檻
        ret = (curr['Close'] / prev['Close'] - 1) * 100
        vol_ratio = curr['Volume'] / curr['VMA5']
        is_money_in = (vol_ratio > 1.2) and (ret >= up_threshold)
        
        # 3. 買點共振：KD 金叉 (今日 K > D, 昨日 K < D)
        is_kd_cross = (curr['K'] > curr['D']) and (prev['K'] <= prev['D'])
        
        if is_bull and is_money_in and is_kd_cross:
            return {
                "股票": f"{ticker.split('.')[0]} {info[ticker]['name']}",
                "產業": info[ticker]['ind'],
                "現價": round(float(curr['Close']), 2),
                "漲幅": round(ret, 2),
                "量比": round(vol_ratio, 2),
                "目標": round(float(curr['Close'] + (curr['ATR'] * 2.5)), 2),
                "支撐": round(float(curr['MA20']), 2),
                "權重": ret + (vol_ratio * 2) # 用於排序
            }
    except: return None
    return None

# --- 4. 主介面設計 ---
st.title("⚡ 2026 台股三位一體強勢掃描")
st.markdown("🎯 **策略核心：** 資金流向 (量能) + 產業集中 (族群) + 趨勢成立 (MA多頭)")

with st.sidebar:
    st.header("🔍 篩選參數")
    up_val = st.slider("突破漲幅門檻 (%)", 0.0, 5.0, 1.5, 0.1)
    limit = st.number_input("掃描數量 (建議前 500 檔)", 50, 2000, 500)
    st.divider()
    if st.button("🧹 清除快取重整"):
        st.cache_data.clear()
        st.rerun()

if st.button("🚀 開始掃描市場主流", use_container_width=True):
    stock_info = load_stock_info()
    tickers = list(stock_info.keys())[:limit]
    
    results = []
    progress_bar = st.progress(0)
    status = st.empty()
    
    # 批次獲取數據
    status.text("正在從 Yahoo Finance 獲取數據...")
    data = yf.download(tickers, period="8mo", group_by='ticker', progress=False)
    
    for i, t in enumerate(tickers):
        try:
            df = data[t].dropna() if len(tickers) > 1 else data.dropna()
            res = analyze_sop(df, t, stock_info, up_val)
            if res:
                results.append(res)
        except: continue
        progress_bar.progress((i + 1) / len(tickers))
    
    status.empty()
    progress_bar.empty()

    if results:
        # 1. 產業集中度分析
        df_res = pd.DataFrame(results).sort_values(by="權重", ascending=False)
        ind_counts = Counter([r['產業'] for r in results])
        
        st.subheader("📊 當前資金集中產業 (族群性)")
        cols = st.columns(3)
        for idx, (ind, count) in enumerate(ind_counts.most_common(3)):
            cols[idx].metric(f"Top {idx+1} {ind}", f"{count} 檔符合", "主流族群")
            
        st.divider()

        # 2. 顯示個股清單
        st.subheader(f"🔥 符合「三位一體」標的 (共 {len(results)} 檔)")
        for _, item in df_res.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([1, 1, 1.5])
                with c1:
                    st.write(f"### {item['股票']}")
                    st.markdown(f"<span class='industry-tag'>{item['產業']}</span>", unsafe_allow_html=True)
                with c2:
                    st.metric("現價", f"{item['現價']}", f"{item['漲幅']}%")
                    st.write(f"📊 量能比：`{item['量比']}x`")
                with c3:
                    st.markdown(f"""
                    <div class="price-box">
                    🔴 波段目標：<span style="color:#FF4B4B;">{item['目標']}</span><br>
                    🔵 關鍵支撐：<span style="color:#4FACFE;">{item['支撐']} (月線)</span>
                    </div>
                    """, unsafe_allow_html=True)
    else:
        st.error("❌ 目前條件下無符合標的。建議嘗試：1. 調降漲幅門檻 2. 擴大掃描數量 3. 等待盤勢回溫。")

st.divider()
st.caption(f"📅 系統執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 投資前請務必獨立判斷風險。")
