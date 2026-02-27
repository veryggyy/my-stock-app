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
    cache_file = "taiwan_stock_list.csv"
    if not os.path.exists(cache_file):
        return {"2330.TW": "台積電"}
    
    try:
        # 嘗試多種編碼讀取 (處理 Excel 存出的 CSV 常見編碼問題)
        try:
            df = pd.read_csv(cache_file, dtype=str, encoding='utf-8-sig')
        except:
            df = pd.read_csv(cache_file, dtype=str, encoding='big5')
            
        df.columns = [c.strip() for c in df.columns]
        # 找尋關鍵欄位 (模糊匹配)
        code_col = next((c for c in df.columns if '代號' in c or 'code' in c.lower()), df.columns[0])
        name_col = next((c for c in df.columns if '名稱' in c or 'label' in c.lower() or '股票' in c), df.columns[1])
        
        # 清洗代號：只留數字，並補上 .TW
        df['clean_code'] = df[code_col].str.extract(r'(\d{4})')
        df = df.dropna(subset=['clean_code'])
        
        return {f"{row['clean_code']}.TW": str(row[name_col]).strip() for _, row in df.iterrows()}
    except Exception as e:
        st.error(f"CSV 讀取錯誤: {e}")
        return {"2330.TW": "台積電"}

# --- 2. 核心分析功能 ---
def fast_analyze(data, order):
    try:
        if len(data) < 40: return None
        # 處理 yfinance 可能回傳的多層結構
        df = data.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        prices = df['Close'].values.flatten().astype(float)
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        curr_price = prices[-1]

        low_idx = argrelextrema(prices, np.less, order=order)
        if len(low_idx[0]) < 2: return None
        
        last_low, prev_low = prices[low_idx[0][-1]], prices[low_idx[0][-2]]

        if last_low > prev_low and curr_price > (ma20 * 0.96):
            return {
                "現價": round(curr_price, 2),
                "支撐價": round(last_low, 2),
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
    sens = st.slider("趨勢靈敏度 (Order)", 2, 10, 4)
    st.info(f"📊 待掃描清單: {len(symbols)} 檔")
    start_btn = st.button("🚀 啟動極速掃描")

if start_btn:
    if not symbols:
        st.error("❌ 掃描清單為空！請檢查 CSV 檔案中的『代號』欄位是否正確。")
    else:
        all_results = []
        progress_bar = st.progress(0)
        
        with st.spinner(f"正在分析 {len(symbols)} 檔數據..."):
            # 採用批量下載 (增加穩定性參數)
            try:
                raw_data = yf.download(symbols, period="6mo", group_by='ticker', threads=True, progress=False)
                
                for idx, (sym, name) in enumerate(stock_dict.items()):
                    try:
                        # 確保提取該股數據
                        stock_df = raw_data[sym] if len(symbols) > 1 else raw_data
                        res = fast_analyze(stock_df, sens)
                        if res:
                            res.update({"股票名稱": name, "代號": sym.split('.')[0]})
                            all_results.append(res)
                    except: continue
                    if idx % 50 == 0: progress_bar.progress((idx+1)/len(symbols))
            except Exception as e:
                st.error(f"下載失敗: {e}")

        if all_results:
            st.success(f"發現 {len(all_results)} 檔符合標的")
            st.dataframe(pd.DataFrame(all_results).sort_values(by="風險距離%"), use_container_width=True)
        else:
            st.warning("查無符合標的。")

st.markdown("---")
st.caption("修正：加入 CSV 自動編碼偵測與空值防護。")
