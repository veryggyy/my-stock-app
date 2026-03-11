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
st.set_page_config(page_title="2026 台股強勢波段雷達", layout="wide")

st.markdown("""
    <style>
    .block-container { padding-top: 2rem; }
    h3 { font-size: 1.6rem !important; font-weight: 800; color: #FFD700; margin-bottom: 5px; }
    [data-testid="stMetricValue"] { font-size: 1.8rem !important; color: #00FFCC !important; font-weight: 900; }
    .price-box { 
        font-size: 1.1rem; line-height: 2.0; font-weight: bold; padding: 15px; 
        background: #0f172a; border-radius: 12px; border: 1px solid #374151; 
    }
    .stProgress > div > div > div > div { background-color: #00ffcc; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 獲取大盤環境 (^TWII) - 優化抓取邏輯 ---
def get_market_regime():
    try:
        # 改用 Ticker 模式獲取數據，較不易被封鎖
        twii_ticker = yf.Ticker("^TWII")
        twii = twii_ticker.history(period="6mo")
        
        if twii.empty or len(twii) < 2:
            return "⚠️ 數據源暫時忙碌中", "#FFFFFF", 0.0
            
        twii['MA20'] = ta.sma(twii['Close'], length=20)
        curr_price = twii['Close'].iloc[-1]
        ma20_val = twii['MA20'].iloc[-1]
        daily_ret = (twii['Close'].iloc[-1] / twii['Close'].iloc[-2] - 1) * 100
        
        if curr_price > ma20_val:
            return "🟢 大盤位於月線上 (多頭有利)", "#00FFCC", daily_ret
        else:
            return "🔴 大盤位於月線下 (空頭防禦)", "#FF4B4B", daily_ret
    except Exception as e:
        return f"⚠️ 抓取異常: {str(e)[:10]}", "#FFFFFF", 0.0

# --- 3. 獲取清單 (與原架構一致) ---
@st.cache_data(ttl=600)
def get_full_taiwan_list():
    stocks = {}
    sectors = {}
    file_path = "taiwan_stock_list.csv"
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path, encoding="utf-8-sig")
            for _, row in df.iterrows():
                code = str(row.iloc[0]).strip().upper()
                name = str(row.iloc[1]).strip()
                sec = str(row.iloc[2]).strip() if len(row) > 2 else "未分類"
                if len(code) >= 4 and "代號" not in code:
                    full_code = f"{code}.TW" if not (code.endswith('.TW') or code.endswith('.TWO')) else code
                    stocks[full_code] = name
                    sectors[full_code] = sec
            return stocks, sectors, f"✅ 已載入清單 (共 {len(stocks)} 檔)"
        except: pass
    return {"2330.TW": "台積電", "2317.TW": "鴻海"}, {"2330.TW": "半導體", "2317.TW": "電子代工"}, "⚠️ 使用預設清單"

# --- 4. 核心分析引擎 ---
def analyze_sop_v2026(df, up_threshold):
    try:
        if df is None or len(df) < 65: return None
        df.columns = [str(c).capitalize() for c in df.columns]
        
        df['MA20'] = ta.sma(df['Close'], length=20)
        df['MA60'] = ta.sma(df['Close'], length=60)
        df['MA20_Slope'] = df['MA20'].diff(3) 
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        kd_df = ta.stoch(df['High'], df['Low'], df['Close'], k=14, d=3, smooth_k=3)
        df['K'], df['D'] = kd_df.iloc[:, 0], kd_df.iloc[:, 1]
        df['VMA5'] = ta.sma(df['Volume'], length=5)
        
        curr, prev = df.iloc[-1], df.iloc[-2]
        ret = (float(curr['Close']) / float(prev['Close']) - 1) * 100
        vol_ratio = round(float(curr['Volume'] / curr['VMA5']), 2)
        
        # 多頭邏輯
        is_bull = (curr['Close'] > curr['MA20']) and (curr['MA20'] > curr['MA60'])
        is_slope_up = curr['MA20_Slope'] > 0
        is_kd_cross = (curr['K'] > curr['D']) and (prev['K'] <= prev['D'])
        is_breakout = (vol_ratio > 1.2) and (ret >= up_threshold)
        
        base_res = {"漲幅": ret, "量能比": vol_ratio}
        
        if is_bull and is_slope_up and is_kd_cross and is_breakout:
            atr_val = df['ATR'].iloc[-1]
            base_res.update({
                "符合": True, "現價": round(float(curr['Close']), 2), "K值": int(curr['K']),
                "買進參考": round(float(curr['Close']), 2),
                "賣出參考": round(float(curr['Close'] + (atr_val * 2.5)), 2),
                "支撐參考": round(float(curr['Close'] - (atr_val * 1.5)), 2),
                "評分": ret + (vol_ratio * 2)
            })
            return base_res
        
        base_res["符合"] = False
        return base_res
    except: return None

# --- 5. 主介面 ---
st.title("⚡ 2026 台股強勢波段雷達")
market_msg, market_color, market_ret = get_market_regime()
st.markdown(f"**市場環境：<span style='color:{market_color};'>{market_msg}</span> | 今日大盤漲跌：`{market_ret:.2f}%`**", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 篩選參數")
    ret_target = st.slider("突破漲幅門檻 (%)", 0.0, 5.0, 1.5, 0.5)
    # 修正需求 1：預設值直接設為最大值 3000
    scan_limit = st.number_input("掃描數量", 10, 3000, 3000)
    if st.button("🔄 清除快取"):
        st.cache_data.clear(); st.rerun()

# --- 6. 執行掃描 ---
if st.button("🔵 執行全台股深度掃描 (依評分排序)", use_container_width=True):
    all_stocks, all_sectors, status_msg = get_full_taiwan_list()
    st.info(status_msg)
    
    tickers = sorted(list(all_stocks.keys()))[:int(scan_limit)]
    results, sector_stats = [], []
    
    progress_bar = st.progress(0)
    status_text = st.empty()

    batch_size = 40 
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        status_text.text(f"掃描中: {i+1} ~ {min(i+batch_size, len(tickers))}...")
        try:
            data = yf.download(batch, period="8mo", group_by='ticker', auto_adjust=True, progress=False)
            for sym in batch:
                try:
                    df = data[sym].dropna() if len(batch) > 1 else data.dropna()
                    res = analyze_sop_v2026(df, ret_target)
                    if res:
                        res["產業"] = all_sectors.get(sym, "未分類")
                        sector_stats.append({"產業": res["產業"], "漲幅": res["漲幅"]})
                        if res.get("符合"):
                            res["股票"] = f"{sym.split('.')[0]} {all_stocks[sym]}"
                            results.append(res)
                except: continue
        except: continue
        progress_bar.progress(min((i + batch_size) / len(tickers), 1.0))
    
    status_text.empty(); progress_bar.empty()

    # 產業排行
    st.subheader("📊 產業強弱排行 (目前資金流向)")
    if sector_stats:
        s_df = pd.DataFrame(sector_stats).groupby("產業").mean().sort_values("漲幅", ascending=False)
        cols = st.columns(min(len(s_df), 5))
        for idx, (name, row) in enumerate(s_df.head(5).iterrows()):
            cols[idx].metric(name, f"{row['漲幅']:.2f}%")
    
    st.divider()

    if results:
        results = sorted(results, key=lambda x: x['評分'], reverse=True)
        st.success(f"✅ 找到 {len(results)} 檔多頭起漲標的")
        
        # 匯出 CSV (24H 檔名)
        now_str = datetime.now().strftime("%Y%m%d_%H%M")
        export_df = pd.DataFrame(results).drop(columns=["符合"])
        st.download_button("📥 匯出當下分析清單 (CSV)", export_df.to_csv(index=False).encode('utf-8-sig'), f"taiwan_stocks_{now_str}.csv", "text/csv")
        
        for item in results:
            with st.container(border=True):
                st.write(f"### {item['股票']} ({item['產業']})")
                c1, c2 = st.columns(2)
                # 修正需求 2：漲幅小數點取到整數 (.0f)
                c1.metric("價格", f"{item['現價']}", f"{item['漲幅']:.0f}%")
                c2.write(f"📊 量能比: `{item['量能比']}x` | 📈 K值: `{item['K值']}`")
                st.markdown(f"""
                <div class="price-box">
                🟢 買進參考：<span style="color:#00FF88;">{item['買進參考']}</span><br>
                🔵 關鍵支撐：<span style="color:#4FACFE;">{item['支撐參考']}</span><br>
                🔴 波段目標：<span style="color:#FF4B4B;">{item['賣出參考']}</span>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.error("❌ 目前市場環境較弱，無符合條件標的。")

st.divider()
st.caption("⚠ 免責聲明：此程式僅供技術分析練習，投資請務必配合大盤走勢參考。")
