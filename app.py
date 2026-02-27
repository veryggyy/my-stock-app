import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
import re
import time

# --- 1. 頁面設定 ---
st.set_page_config(page_title="2026 台股趨勢掃描器", layout="wide")

# CSS 優化：改善表格顯示與字體
st.markdown("""
    <style>
    [data-testid="stTable"] { font-size: 18px !important; }
    .stDataFrame td { font-size: 16px !important; }
    .stProgress > div > div > div > div { background-color: #00c853; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 資料獲取與處理函數 ---

@st.cache_data(ttl=3600)
def get_stock_list(limit=200):
    """讀取本地 CSV 清單，若無則提供權值股備援"""
    cache_file = "taiwan_stock_list.csv"
    stocks = {}
    
    if os.path.exists(cache_file):
        try:
            # 嘗試不同編碼讀取 CSV
            df = None
            for enc in ['utf-8-sig', 'big5', 'gbk']:
                try:
                    df = pd.read_csv(cache_file, dtype=str, encoding=enc)
                    break
                except:
                    continue
            
            if df is not None:
                df.columns = [c.strip() for c in df.columns]
                # 自動找尋包含 '代號' 或 'code' 的欄位
                code_col = next((c for c in df.columns if any(k in c for k in ['代號', 'code'])), df.columns[0])
                name_col = next((c for c in df.columns if any(k in c for k in ['名稱', 'label', 'name'])), df.columns[1])
                
                # 限制數量並格式化為 yfinance 代號 (.TW)
                df = df.head(limit)
                for _, row in df.iterrows():
                    code = str(row[code_col]).strip()
                    name = str(row[name_col]).strip()
                    # 補足四位數代號 (針對如 0050)
                    if len(code) == 2: code = "00" + code
                    stocks[f"{code}.TW"] = name
        except Exception as e:
            st.error(f"讀取 CSV 發生錯誤: {e}")
    
    if not stocks:
        # 備援清單
        stocks = {"2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電", "2382.TW": "廣達"}
        st.info("💡 採用內建預設權值股清單。")
        
    return stocks

def analyze_trend_strategy(df, symbol, name):
    """核心技術分析邏輯"""
    try:
        if df is None or len(df) < 60:
            return None
        
        # 處理多重索引 (yfinance 批次下載時會產生)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # 計算技術指標
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        df['VMA20'] = df['Volume'].rolling(20).mean()
        
        # MACD 計算
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - signal_line

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 趨勢過濾：多頭排列
        trend_ok = curr['MA20'] > curr['MA60']
        if not trend_ok:
            return None

        # 型態判定
        is_breakout = (curr['Close'] > prev['High']) and (curr['Volume'] > curr['VMA20'] * 1.5)
        is_support = (curr['Low'] <= curr['MA20'] * 1.02) and (curr['Close'] >= curr['MA20'] * 0.99) and (macd_hist.iloc[-1] > 0)

        if is_breakout or is_support:
            # 優先級分值
            score = (2 if is_breakout else 1) + (1 if macd_hist.iloc[-1] > 0 else 0)
            clean_name = re.split(r'[\s0-9]', name)[0] # 去除名稱中的數字與空格
            
            return {
                "優先級": score,
                "代號": symbol.split('.')[0],
                "股票名稱": clean_name,
                "現價": round(float(curr['Close']), 2),
                "MA20參考": round(float(curr['MA20']), 2),
                "型態": "🚀 帶量突破" if is_breakout else "📉 回測支撐",
                "MACD": "🔴 紅柱" if macd_hist.iloc[-1] > 0 else "🟢 綠柱",
                "成交量": "🔥 爆量" if curr['Volume'] > curr['VMA20'] * 1.5 else "正常"
            }
    except:
        return None
    return None

# --- 3. UI 主界面 ---

st.title("⚡ TW 2026 極速趨勢掃苗器")
st.caption("穩定版 | 已優化連線機制與錯誤捕捉")

# 側邊欄設定
with st.sidebar:
    st.header("⚙️ 掃描設定")
    scan_limit = st.slider("掃描檔數限制", 50, 500, 200)
    stock_dict = get_stock_list(limit=scan_limit)
    symbols = list(stock_dict.keys())
    
    st.info(f"📊 目前清單共: {len(symbols)} 檔")
    start_btn = st.button("🚀 開始掃描", use_container_width=True)

# 執行掃描
if start_btn:
    all_results = []
    
    # 使用 st.status 提供更好的 UI 體驗，避免「轉圈圈」的枯燥感
    with st.status("🔍 正在下載資料並進行分析...", expanded=True) as status:
        batch_size = 40  # 縮小批次以增加穩定性
        prog_bar = st.progress(0)
        
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            status.write(f"正在分析第 {i+1} ~ {min(i+batch_size, len(symbols))} 檔...")
            
            try:
                # 下載數據，設定 auto_adjust 避免索引混亂
                raw_data = yf.download(
                    batch, 
                    period="6mo", 
                    group_by='ticker', 
                    threads=True, 
                    progress=False,
                    auto_adjust=True
                )
                
                for sym in batch:
                    try:
                        # 處理單檔與多檔下載的資料結構差異
                        df = raw_data[sym] if len(batch) > 1 else raw_data
                        if df.empty or len(df) < 20: continue
                        
                        res = analyze_trend_strategy(df, sym, stock_dict[sym])
                        if res:
                            all_results.append(res)
                    except:
                        continue
            except Exception as e:
                status.write(f"❌ 批次下載失敗，跳過該組: {e}")
                
            prog_bar.progress(min((i + batch_size) / len(symbols), 1.0))
            time.sleep(0.5) # 微小延遲防止被 Yahoo 封鎖
            
        status.update(label="✅ 掃描完成！", state="complete", expanded=False)

    # 顯示結果
    if all_results:
        df_res = pd.DataFrame(all_results).sort_values(by=["優先級", "現價"], ascending=[False, True])
        
        st.subheader(f"💡 篩選出 {len(all_results)} 檔優選標的")
        st.dataframe(
            df_res.drop(columns=['優先級']), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "代號": st.column_config.TextColumn("代號"),
                "現價": st.column_config.NumberColumn("現價", format="%.2f"),
                "MA20參考": st.column_config.NumberColumn("買進參考", format="%.2f"),
            }
        )
    else:
        st.warning("當前盤勢下，查無符合多頭排列與進場條件的股票。")

st.divider()
st.caption("免責聲明：本工具僅供參考，投資前請自行評估風險。")
