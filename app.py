import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta  # 請在 requirements.txt 加入 pandas_ta
import time
import os

# --- 1. 頁面設定 ---
st.set_page_config(page_title="2026 精準波段 SOP 掃描器", layout="wide")

@st.cache_data(ttl=3600)
def get_stock_list():
    cache_file = "taiwan_stock_list.csv"
    if not os.path.exists(cache_file):
        return {"2330.TW": "台積電", "2317.TW": "鴻海"}
    try:
        df = pd.read_csv(cache_file, dtype=str, encoding='utf-8-sig')
        # 自動識別欄位
        c_col = next((c for c in df.columns if any(k in c for k in ['Symbol', '代號', 'code'])), df.columns[0])
        n_col = next((c for c in df.columns if any(k in c for k in ['Name', '名稱', 'label'])), df.columns[1])
        return {f"{str(row[c_col]).strip()[:4]}.TW": str(row[n_col]).strip() for _, row in df.iterrows()}
    except:
        return {"2330.TW": "台積電"}

# --- 2. 核心 SOP 分析引擎 ---
def analyze_2026_sop(df, vol_mult):
    if len(df) < 60: return None
    
    # 計算技術指標 (使用 pandas_ta)
    df['MA5'] = ta.sma(df['Close'], length=5)
    df['MA10'] = ta.sma(df['Close'], length=10)
    df['MA20'] = ta.sma(df['Close'], length=20)
    df['MA60'] = ta.sma(df['Close'], length=60)
    df['VMA20'] = ta.sma(df['Volume'], length=20)
    
    # MACD
    macd = ta.macd(df['Close'])
    df['MACD_h'] = macd['MACDh_12_26_9'] # 柱狀圖
    
    # KD (9,3,3)
    kd = ta.stoch(df['High'], df['Low'], df['Close'])
    df['K'] = kd['STOCHk_14_3_3']
    df['D'] = kd['STOCHd_14_3_3']

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # 【SOP 條件篩選】
    # 1. 趨勢確立：股價在 20MA 與 60MA 之上 (中期看漲)
    is_bullish = curr['Close'] > curr['MA20'] and curr['Close'] > curr['MA60']
    
    # 2. 進場訊號 A：帶量突破 + MACD 轉正 (起漲點)
    is_breakout = (curr['Close'] > prev['High']) and (curr['Volume'] > curr['VMA20'] * vol_mult) and (curr['MACD_h'] > 0 > prev['MACD_h'])
    
    # 3. 進場訊號 B：KD 低檔黃金交叉 (回測買點)
    is_kd_cross = (prev['K'] < 30) and (curr['K'] > curr['D']) and (prev['K'] <= prev['D'])

    if is_bullish and (is_breakout or is_kd_cross):
        return {
            "型態": "🚀 帶量突破" if is_breakout else "🎯 KD 低檔金叉",
            "現價": round(curr['Close'], 2),
            "MA20": round(curr['MA20'], 2),
            "量能": f"{round(curr['Volume']/curr['VMA20'], 1)}x",
            "KD值": f"K:{int(curr['K'])}",
            "防守點": round(curr['MA20'] * 0.97, 2), # 以月線下方 3% 為動態停損
            "優先級": 1 if is_breakout else 2
        }
    return None

# --- 3. UI 介面 ---
st.title("⚡ 2026 短中期操作 SOP 掃描器")
st.markdown("> **策略邏輯：** 股價需站穩 **20/60MA**，尋找 **MACD 由負轉正** 或 **KD 低檔金叉** 之標的。")

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
    progress_bar = st.progress(0)
    
    # 批次下載數據以提升速度
    data = yf.download(symbols, period="6mo", group_by='ticker', threads=True, progress=False)
    
    for idx, (sym, name) in enumerate(stock_dict.items()):
        try:
            stock_df = data[sym].copy() if len(symbols) > 1 else data.copy()
            res = analyze_2026_sop(stock_df, vol_target)
            if res:
                res["股票"] = f"{sym.split('.')[0]} {name}"
                results.append(res)
        except: continue
        progress_bar.progress((idx + 1) / len(symbols))

    # --- 4. 結果呈現 ---
    if results:
        df_res = pd.DataFrame(results).sort_values("優先級")
        st.subheader(f"🎯 依據 SOP 篩選出 {len(results)} 檔標的")
        
        cols = st.columns(3) # 手機版建議改為 1 或 2
        for i, row in enumerate(results):
            with cols[i % 3].container(border=True):
                st.write(f"### {row['股票']}")
                st.info(f"**訊號：{row['型態']}**")
                st.metric("目前價格", row['現價'], f"支撐 {row['MA20']}")
                st.write(f"📊 量能：`{row['量能']}` | `{row['KD值']}`")
                st.warning(f"🛡️ 建議防守點：{row['防守點']}")
    else:
        st.warning("當前盤勢無符合 SOP 之標的，建議觀望或調降量能門檻。")

st.divider()
st.caption("⚠ 免責聲明：本工具僅供技術分析參考，不構成投資建議。2026 年操作請嚴格執行停損。")
