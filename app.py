import streamlit as st
import pandas as pd
import requests
import ssl
from io import StringIO
import urllib3

# --- 核心修復：徹底關閉 SSL 檢查 ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

@st.cache_data(ttl=86400)
def get_full_taiwan_stock_list():
    stocks = []
    # 模擬真實瀏覽器，增加連線成功率
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    }
    
    # 證交所正確的公開清單網址 (上市Mode=2, 上櫃Mode=4)
    targets = [
        ("https://isin.twse.com.tw", ".TW"),
        ("https://isin.twse.com.tw", ".TWO")
    ]
    
    session = requests.Session() # 使用 Session 增加連線穩定度
    
    try:
        for url, suffix in targets:
            # 關鍵修正：verify=False 強制忽略 SSL 錯誤
            response = session.get(url, headers=headers, verify=False, timeout=30)
            response.encoding = 'big5'
            
            # 使用 pd.read_html 解析
            df_list = pd.read_html(StringIO(response.text))
            if not df_list: continue
            
            df = df_list[0]
            # 處理表格標頭
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            for item in df['有價證券代號及名稱']:
                if pd.isna(item): continue
                parts = item.replace('　', ' ').split(' ')
                if len(parts) >= 2:
                    code, name = parts[0], parts[1]
                    # 只抓取 4 碼純數字普通股
                    if len(code) == 4 and code.isdigit():
                        stocks.append({"label": name, "code": code, "symbol": f"{code}{suffix}"})
        
        return stocks
    except Exception as e:
        # 如果還是失敗，顯示具體錯誤，方便除錯
        st.error(f"連線證交所失敗：{str(e)}")
        return []

# --- 剩餘分析邏輯保持不變 ---
