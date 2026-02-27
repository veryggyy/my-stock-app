import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import os

# --- 1. 頁面設定 ---
st.set_page_config(page_title="2026 台股極速掃描系統", layout="wide")

@st.cache_data(ttl=3600)
def get_stock_list():
    """超強健 CSV 讀取：自動校正欄位與編碼"""
    cache_file = "taiwan_stock_list.csv"
    fallback = {"2330.TW": "台積電"}
    
    if not os.path.exists(cache_file): return fallback
    
    try:
        for enc in ['utf-8-sig', 'big5', 'gbk']:
            try:
                df = pd.read_csv(cache_file, dtype=str, encoding=enc)
                break
            except: continue
        
        df.columns = [c.strip() for c in df.columns]
        code_col = next((c for c in df.columns if any(k in c for k in ['代號', 'code', 'Code'])), df.columns[0])
        name_col = next((c for c in df.columns if any(k in c for k in ['名稱', 'label', 'Name'])), df.columns[min(1, len(df.columns)-1)])
        
        df['clean_code'] = df[code_col].str.extract(r'(\d{4})')
        df = df.dropna(subset=['clean_code'])
        
        if df.empty: return fallback
        return {f"{row['clean_code']}.TW": str(row[name_col]).strip() for _, row in df.iterrows()}
    except Exception as e:
        st.error(f"CSV 讀取錯誤: {e}")
        return fallback

# --- 2. 核心分析功能 ---
def fast_analyze(data, order):
    try:
        if data is None or len(data) < 40: return None
        
        df = data.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        prices = df['Close'].values.flatten().astype(float)
        if len(prices[~np.isnan(prices)]) < 40: return None
        
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        curr_price = prices[-1]

        low_idx = argrelextrema(prices, np.less, order=order)[0]
        if len(low_idx) < 2: return None
        
        last_low = prices[low_idx[-1]]
        prev_low = prices[low_idx[-2]]

        # 核心條件：底底高 + 現價不低於月線 4%
        if last_low > prev_low and curr_price > (ma20 * 0.96):
            return {
                "現價": round(curr_price, 2),
                "建議買進價格": round(last_low, 2),  # 以支撐價作為建議買點
                "賣出價格": round(last_low * 1.15, 2), # 範例：支撐價 + 15% 作為目標
                "風險距離%": round((curr_price/last_low-1)*100, 1),
                "成交量": "🔥 爆量" if df['Volume'].iloc[-1] > df['Volume'].rolling(20).mean().iloc[-1]*1.5 else "正常"
            }
    except: return None
    return None

# --- 3. UI 介面 ---
st.title("⚡ TW 2026 極速趨勢掃描器")
stock_dict = get_stock_list()
symbols = list(stock_dict.keys())

with st.sidebar:
    st.header("⚙️ 參數設定")
    sens = st.slider("趨勢靈敏度 (Order)", 2, 12, 4)
    st.info(f"📊 待掃描清單: {len(symbols)} 檔")
    start_btn = st.button("🚀 啟動極速掃描")

if start_btn:
    if not symbols:
        st.error("❌ 掃描清單為空！請檢查 CSV 資料。")
    else:
        all_results = []
        progress_bar = st.progress(0)
        
        with st.spinner(f"正在極速下載並分析 {len(symbols)} 檔台股..."):
            try:
                raw_data = yf.download(symbols, period="6mo", group_by='ticker', threads=True, progress=False)
                
                for idx, (sym, name) in enumerate(stock_dict.items()):
                    try:
                        stock_df = raw_data[sym] if len(symbols) > 1 else raw_data
                        if stock_df.empty: continue
                        
                        res = fast_analyze(stock_df, sens)
                        if res:
                            # 重新排列字典順序：名稱與代號置前
                            final_res = {
                                "代號": sym.split('.')[0],
                                "股票名稱": name
                            }
                            final_res.update(res)
                            all_results.append(final_res)
                    except: continue
                    
                    if idx % 100 == 0: 
                        progress_bar.progress(min((idx + 1) / len(symbols), 1.0))
                
                progress_bar.progress(1.0)
            except Exception as e:
                st.error(f"下載過程發生錯誤: {e}")

        if all_results:
            st.success(f"發現 {len(all_results)} 檔符合型態標的")
            # 轉換為 DataFrame 並依「現價」低至高排序
            result_df = pd.DataFrame(all_results).sort_values(by="現價", ascending=True)
            st.dataframe(result_df, use_container_width=True, hide_index=True)
        else:
            st.warning("查無符合標的。建議將「靈敏度」調低。")

st.markdown("---")
st.caption("調整：已將代號名稱移至左側，並依現價由低至高排序。")
