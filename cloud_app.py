"""Public entrypoint. Each browser session gets separate experiment databases."""
import runpy
from pathlib import Path
import streamlit as st

st.session_state['_cash_cloud'] = True
runpy.run_path(str(Path(__file__).with_name('app.py')), run_name='__main__')
