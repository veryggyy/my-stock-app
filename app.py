@st.cache_data(ttl=86400)
def get_full_taiwan_stock_list():
    cache_file = "taiwan_stock_list.csv"
    if os.path.exists(cache_file):
        try:
            # 讀取時不指定 header，先看前兩行長怎樣
            df = pd.read_csv(cache_file, dtype=str)
            
            # 清除欄位名稱的空白與逗號
            df.columns = [c.strip().replace(',', '') for c in df.columns]
            
            # 偵錯用：如果還是噴錯，顯示欄位名稱給使用者看
            if 'symbol' not in df.columns:
                # 嘗試自動修復：如果第一欄是標籤，第二欄是代號
                if len(df.columns) >= 2:
                    df.columns = ['label', 'code', 'symbol'][:len(df.columns)]
                    if 'symbol' not in df.columns:
                        df['symbol'] = df['code'] + ".TW"
                else:
                    st.error(f"CSV 格式不符！偵測到的欄位有：{list(df.columns)}")
                    return []

            # 清理資料內容
            for col in df.columns:
                df[col] = df[col].str.strip().str.replace(',', '')
                
            return df.to_dict('records')
        except Exception as e:
            st.error(f"讀取 CSV 失敗: {e}")
            
    return [{"label": "台積電", "code": "2330", "symbol": "2330.TW"}]
