import streamlit as st
import pandas as pd

st.title("🚀 離線測試模式")

if st.button("點擊測試 UI 反應"):
    data = {"股票": ["台積電", "鴻海"], "價格": [1000, 200]}
    st.table(pd.DataFrame(data))
    st.success("UI 正常，代表問題出在網路連線或 yfinance。")
