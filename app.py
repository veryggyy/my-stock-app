import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time
import os

# --- 1. 頁面設定 ---
st.set_page_config(page_title="2026 精準波段 SOP 掃描器", layout="wide")

@st.cache_data(ttl=3600)
def get_stock_list():
    # 預設清單或讀取 CSV
    return {"2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電", "2382.TW": "廣達"}

# --- 2. 核心 SOP 分析引擎 ---
def analyze_2026_sop(df, vol_mult):
    if df is None or len(df) < 60: return None
    
    # 計算技術指標
    df['MA20'] = ta.sma(df['Close'], length=20)
    df['MA60'] = ta.sma(df['Close'], length=60)
    df['VMA20'] = ta.sma(df['Volume'], length=20)
    
    macd = ta.macd(df['Close'])
    df['MACD_h'] = macd['MACDh_12_26_9']
    
    kd = ta.stoch(df['High'], df['Low'], df['Close'])
    df['K'] = kd['STOCHk_14_3_3']
    df['D'] = kd['STOCHd_14_3_3']

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    is_bullish = curr['Close'] > curr['MA20'] and curr['Close'] > curr['MA60']
    is_breakout = (curr['Close'] > prev['High']) and (curr['Volume'] > curr['VMA20'] * vol_mult) and (curr['MACD_h'] > 0 > prev['MACD_h'])
    is_kd_cross = (prev['K'] < 30) and (curr['K'] > curr['D']) and (prev['K'] <= prev['D'])

    if is_bullish and (is_breakout or is_kd_cross):
        return {
            "型態": "🚀 帶量突破" if is_breakout else "🎯 KD 低檔金叉",
            "現價": round(curr['Close'], 2),
            "MA20": round(curr['MA20'], 2),
            "量能": f"{round(curr['Volume']/curr['VMA20'], 1)}x",
            "KD值": f"K:{int(curr['K'])}",
            "防守點": round(curr['MA20'] * 0.97, 2),
            "優先級": 1 if is_breakout else 2
        }
    return None

# --- 3. UI 介面 ---
st.title("⚡ 2026 短中期操作 SOP 掃描器")
st.markdown("> **策略邏輯：** 股價需站穩 **20/60MA**，尋找 **MACD 由負轉正** 或 **KD 低檔金叉**。")

stock_dict = get_stock_list()
symbols = list(stock_dict.keys())

with st.sidebar:
    st.header("⚙️ 參數設定")
    vol_target = st.slider("成交量倍數門檻", 0.5, 3.0, 1.2, 0.1)
    if st.button("🔄 清除快取並重新掃描"):
        st.cache_data.clear()
    start_btn = st.button("🚀 開始分析", use_container_width=True)

if start_btn:
    results = []
    # 建立進度容器
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    start_time = time.time()
    
    # 批次下載
    data = yf.download(symbols, period="6mo", group_by='ticker', threads=True, progress=False)
    
    total = len(symbols)
    for idx, (sym, name) in enumerate(stock_dict.items()):
        # 計算進度資訊
        processed = idx + 1
        percent = int((processed / total) * 100)
        
        # 預估剩餘時間 (ETA)
        elapsed_time = time.time() - start_time
        avg_time_per_stock = elapsed_time / processed
        eta = int(avg_time_per_stock * (total - processed))
        
        # 更新進度條文字 (顯示百分比與秒數)
        progress_text.markdown(f"**分析中... {percent}%** (預計還需 {eta} 秒)")
        progress_bar.progress(processed / total)
        
        try:
            stock_df = data[sym].copy() if total > 1 else data.copy()
            res = analyze_2026_sop(stock_df, vol_target)
            if res:
                res["股票"] = f"{sym.split('.')[0]} {name}"
                results.append(res)
        except: continue

    progress_text.success(f"✅ 分析完成！費時 {int(time.time() - start_time)} 秒")

    # --- 4. 結果呈現 (手機優化) ---
    if results:
        df_res = pd.DataFrame(results).sort_values("優先級")
        st.subheader(f"🎯 篩選出 {len(results)} 檔標的")
        
        # 手機版邏輯：利用 container 建立卡片流
        for row in results:
            with st.container(border=True):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.write(f"### {row['股票']}")
                    st.info(f"**訊號：{row['型態']}**")
                with c2:
                    st.metric("目前價格", row['現價'])
                
                # 橫向顯示詳細數據
                sub_c1, sub_c2, sub_c3 = st.columns(3)
                sub_c1.caption("📊 量能")
                sub_c1.write(f"`{row['量能']}`")
                sub_c2.caption("📉 KD值")
                sub_c2.write(f"`{row['KD值']}`")
                sub_c3.caption("🛡️ 防守點")
                sub_c3.write(f"**{row['防守點']}**")
    else:
        st.warning("當前盤勢無符合 SOP 之標的。")

st.divider()
st.caption("⚠ 免責聲明：本工具僅供技術分析參考，2026 年操作請嚴格執行停損。")
