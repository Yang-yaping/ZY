"""Public entrypoint isolation through the live command adapter."""
import secrets
import sys
from pathlib import Path
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ecash.runtime import DEMO_PASSWORD
first=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
second=AppTest.from_file(str(ROOT/'cloud_app.py'),default_timeout=30).run()
assert not first.exception and not second.exception
lab=first.session_state['_live_lab'];other=second.session_state['_live_lab']
assert lab.root!=other.root

def run(action,**kw):
    result=lab.handle({'id':secrets.token_hex(12),'action':action,'payload':dict(name='alice',password=DEMO_PASSWORD,**kw)})
    assert result['ok'],result
    return result
wid=run('prepare',n=4,t=8)['wallet_id'];run('submit',wid=wid);run('issue',wid=wid)
assert lab.bank.account('alice',DEMO_PASSWORD)['balance']==90
assert other.bank.account('alice',DEMO_PASSWORD)['balance']==100
print('PASS: both public entrypoints, live command withdrawal, visitor isolation')
