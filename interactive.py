"""Native Streamlit bidirectional component, not a screenshot or linked iframe."""
from pathlib import Path

import streamlit as st
from streamlit.components.v2 import component

from ecash.runtime import session_root
from live_lab import LiveLab

ROOT=Path(__file__).resolve().parent


@st.cache_resource(show_spinner=False)
def live_component(version):
    folder=ROOT/'web/live'
    js=(ROOT/'web/showcase/motion-core.js').read_text()+'\nconst YinbiMotion=globalThis.YinbiMotion;\n'+(folder/'controller.js').read_text()
    return component('yinbi_live',html=(folder/'index.html').read_text(),
                     css=(folder/'styles.css').read_text(),js=js,isolate_styles=True)


def main(initial=0):
    st.markdown('''<style>
html,body,.stApp{background:#020708!important;overflow:hidden!important}
[data-testid="stSidebar"],[data-testid="stHeader"],[data-testid="stToolbar"],footer{display:none!important}
[data-testid="stMain"]{height:100dvh;overflow:hidden!important}
[data-testid="stMainBlockContainer"]{padding:0!important;max-width:none!important;height:100dvh}
[data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]{gap:0!important}
</style>''',unsafe_allow_html=True)
    if '_live_lab' not in st.session_state:
        st.session_state['_live_lab']=LiveLab(session_root(st.session_state))
    lab=st.session_state['_live_lab']

    def on_action():
        event=st.session_state['yinbi_interactive'].action
        if event is not None:
            lab.handle(event)

    data=lab.snapshot()
    base=st.get_option('server.baseUrlPath').strip('/')
    data['assets']=('/'+base if base else '')+'/app/static/scenes/'
    names=['home','bank','nodes','coursework']
    requested=st.query_params.get('section')
    data['initial']=names.index(requested) if requested in names else initial
    version=':'.join(str(p.stat().st_mtime_ns) for p in (ROOT/'web/live').iterdir() if p.is_file())
    live_component(version)(key='yinbi_interactive',data=data,height='stretch',on_action_change=on_action)
