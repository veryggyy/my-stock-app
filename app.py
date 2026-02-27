import streamlit as st
import yfinance as yf
import pandas as pd
import time

st.set_page_config(page_title="診斷模式 - 穩定版", layout="wide")

st.title("🛠️ 診斷模式：台股掃描器")
st.write("如果這頁還在轉圈，表示您的網路環境或 Python 環境完全封鎖了連線。")

# 測試用極簡清單
test_stocks = {
    "2330.TW": "台積電",
    "2317.TW": "鴻海",
    "2454.TW": "聯發科",
    "0050.TW": "元大台灣50"
}

if st.button("🚀 開始測試連線 (僅 4 檔)"):
    results = []
    progress_text = st.empty()
    
    for i, (code, name) in enumerate(test_stocks.items()):
        progress_text.text(f"正在嘗試抓取: {code} {name}...")
        try:
            # 關鍵：加入 proxy=None 避免環境變數干擾，縮短 period
            ticker = yf.Ticker(code)
            # 使用 fast_info 快速檢查連線
            df = ticker.history(period="1mo", timeout=10) 
            
            if not df.empty:
                price = df['Close'].iloc[-1]
                results.append({"股票": name, "代號": code, "現價": round(price, 2)})
                st.success(f"✅ {code} 抓取成功")
            else:
                st.warning(f"⚠️ {code} 無資料")
                
        except Exception as e:
            st.error(f"❌ {code} 發生錯誤: {str(e)}")
        
        time.sleep(1) # 避開請求過快

    if results:
        st.write("### 測試結果")
        st.table(pd.DataFrame(results))
    else:
        st.error("所有股票均抓取失敗，請檢查網路連線。")

st.markdown("""
---
### 💡 如果還是轉圈圈，請依序檢查：
1. **關閉 VPN/代理伺服器**：yfinance 對代理伺服器非常敏感。
2. **升級 yfinance**：在終端機輸入 `pip install --upgrade yfinance`。
3. **更換瀏覽器**：有時候是 Brave 或某些擴充功能擋住了 Streamlit 的 WebSocket 連線。
4. **更換網路**：嘗試使用手機熱點。
""")
