import streamlit as st
import yfinance as yf
import pandas as pd
from scipy.signal import argrelextrema
import numpy as np
import time
import os

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="2026 台股趨勢終極掃描系統", layout="wide")

@st.cache_data(ttl=86400)
def get_full_taiwan_stock_list():
    """修正版：自動處理 CSV 中多餘的逗號與格式問題"""
    cache_file = "taiwan_stock_list.csv"
    
    if os.path.exists(cache_file):
        try:
            # 讀取 CSV，並確保所有欄位先以字串處理
            df = pd.read_csv(cache_file, sep=None, engine='python', dtype=str)
            
            # 清除欄位名稱與內容中可能存在的空白或多餘逗號
            df.columns = [c.strip() for c in df.columns]
            for col in df.columns:
                df[col] = df[col].str.strip().str.strip(',')

            # 確保必要的欄位存在，若無則自動生成
            if 'symbol' not in df.columns and 'code' in df.columns:
                df['symbol'] = df['code'] + ".TW"
            if 'label' not in df.columns:
                df['label'] = df.get('code', '未知股票')

            return df.to_dict('records')
        except Exception as e:
            st.error(f"讀取 CSV 失敗: {e}")

    # 保底資料
    return [{"label": "台積電", "code": "2330", "symbol": "2330.TW"}]

# --- 2. 核心分析邏輯 ---
def analyze_chunk(df_batch, selected_stocks_chunk, order):
    results = []
    if df_batch is None or df_batch.empty:
        return results

    for s in selected_stocks_chunk:
        symbol = s['symbol']
        try:
            # yfinance 下載多檔時會產生 MultiIndex
            if symbol not in df_batch: continue
            
            data = df_batch[symbol].dropna()
            if len(data) < 40: continue
            
            close_series = data['Close']
            vol_series = data['Volume']
            prices = close_series.values
            
            # RSI(14)
            delta = close_series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rsi = 100 - (100 / (1 + (gain / loss)))
            curr_rsi = rsi.iloc[-1]
            
            # 成交量暴增 (2倍均量)
            avg_vol = vol_series.rolling(20).mean().iloc[-1]
            curr_vol = vol_series.iloc[-1]
            vol_spike = curr_vol > (avg_vol * 2)
            
            # 底底高判斷
            low_idx = argrelextrema(prices, np.less, order=order)[0]
            if len(low_idx) < 2: continue
            
            curr_price = float(prices[-1])
            ma20 = float(close_series.rolling(20).mean().iloc[-1])
            last_low = float(prices[low_idx[-1]])
            prev_low = float(prices[low_idx[-2]])
            
            # 策略：底底高 + 站上 20MA + RSI < 70
            if last_low > prev_low and curr_price > ma20 and curr_rsi < 70:
                support_price = round(last_low, 2)
                results.append({
                    "股票名稱": s['label'],
                    "代號": s['code'],
                    "現價": round(curr_price, 2),
                    "RSI(14)": round(curr_rsi, 1),
                    "成交量狀態": "🔥 爆量" if vol_spike else "正常",
                    "建議買進區間": f"{round(support_price*1.01, 2)}-{round(support_price*1.05, 2)}",
                    "支撐價位": support_price,
                    "停利目標": round(curr_price * 1.15, 2),
                    "停損價位": round(support_price * 0.97, 2),
                    "風險距離(%)": round((curr_price/support_price-1)*100, 1)
                })
        except:
            continue
    return results

# --- 3. UI 介面 ---
st.title("🛡️ TW 2026 全台股趨勢終極掃描系統")
all_stocks = get_full_taiwan_stock_list()

with st.sidebar:
    st.header("📊 掃描與排序設定")
    sort_option = st.selectbox(
        "結果排序方式", 
        ["風險距離(%) 由小到大", "價位由高到低", "價位由低到高", "RSI 強弱"]
    )
    sens = st.slider("趨勢靈敏度 (Order)", 5, 20, 8)
    start_btn = st.button("🔥 啟動全台股深度掃描")

if start_btn:
    total_count = len(all_stocks)
    chunk_size = 30 # 稍微縮小 chunk 提高穩定度
    all_results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with st.spinner("正在下載數據並分析..."):
        for i in range(0, total_count, chunk_size):
            chunk = all_stocks[i : i + chunk_size]
            symbols = [s['symbol'] for s in chunk]
            status_text.text(f"掃描進度: {i} / {total_count}")
            
            try:
                # 下載資料
                df_batch = yf.download(symbols, period="6mo", progress=False, group_by='ticker')
                if not df_batch.empty:
                    res = analyze_chunk(df_batch, chunk, sens)
                    all_results.extend(res)
            except Exception as e:
                st.warning(f"批次下載發生錯誤，跳過該組。")
            
            progress_bar.progress(min((i + chunk_size) / total_count, 1.0))
            time.sleep(0.6)

    status_text.text("✅ 掃描完成！")

    if all_results:
        final_df = pd.DataFrame(all_results)
        
        # 排序
        if sort_option == "風險距離(%) 由小到大":
            final_df = final_df.sort_values(by="風險距離(%)")
        elif sort_option == "價位由高到低":
            final_df = final_df.sort_values(by="現價", ascending=False)
        elif sort_option == "價位由低到高":
            final_df = final_df.sort_values(by="現價", ascending=True)
        else:
            final_df = final_df.sort_values(by="RSI(14)", ascending=False)

        st.success(f"🎉 找到 {len(final_df)} 檔符合條件標的。")
        
        # 視覺化
        st.dataframe(
            final_df.style.applymap(lambda x: 'background-color: #3d1c1c' if x == "🔥 爆量" else '', subset=['成交量狀態']),
            use_container_width=True
        )
    else:
        st.warning("☹️ 目前條件下未發現符合標的，請嘗試調低靈敏度。")
