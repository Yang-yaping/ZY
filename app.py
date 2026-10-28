"""All public routes run the same live, session-bound designed interface."""
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
navigation = st.navigation({'课程页面':[
    st.Page('showcase.py',title='全屏首页',icon='🏠',default=True),
    st.Page('bank_page.py',title='线上银行',icon='💵',url_path='bank'),
    st.Page('node_page.py',title='节点模拟器',icon='🔗',url_path='p2p'),
    st.Page('coursework_page.py',title='课程作业',icon='📖',url_path='coursework'),
]})
navigation.run()
