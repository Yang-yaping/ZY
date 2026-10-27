"""Shared entrypoint for two independent teaching experiments."""
import sys
from pathlib import Path

import streamlit as st

PROJECT = Path(__file__).resolve().parent
# Keep the delivered P2P core and dataset paths intact. Its standalone CLI tools
# continue to run from p2p/ and do not import the electronic cash implementation.
if str(PROJECT/'p2p') not in sys.path:
    sys.path.insert(0,str(PROJECT/'p2p'))

st.set_page_config(page_title='隐币实验室',page_icon='◈',layout='wide')
st.sidebar.title('◈ 隐币实验室')
st.sidebar.caption('密码学与区块链 · 课程实验工作台')
navigation = st.navigation({'实验项目':[
    st.Page('cash_app.py',title='离线电子现金',icon='💵',default=True,url_path='cash'),
    st.Page('p2p/app.py',title='P2P 网络与区块同步',icon='🔗',url_path='p2p'),
]})
navigation.run()
