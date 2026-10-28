"""All public routes share the live service; visitors stay isolated."""
import secrets
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from ecash.runtime import DEMO_PASSWORD
ROOT=Path(__file__).resolve().parents[1]

class NavigationTests(unittest.TestCase):
    def test_live_routes_preserve_wallet_and_node_result(self):
        app=AppTest.from_file(str(ROOT/'cloud_app.py'),default_timeout=40).run()
        self.assertFalse(app.exception)
        lab=app.session_state['_live_lab']
        def command(action,**p):
            result=lab.handle({'id':secrets.token_hex(12),'action':action,'payload':p})
            self.assertTrue(result['ok'],result)
            return result
        auth=dict(name='alice',password=DEMO_PASSWORD)
        wid=command('prepare',**auth,n=4,t=8)['wallet_id']
        command('submit',**auth,wid=wid);command('issue',**auth,wid=wid)
        command('p2p_run',size=65536,count=3,profile='normal',optimized=True,workers=4)
        for file in ('bank_page.py','node_page.py','coursework_page.py','showcase.py'):
            app.switch_page(file).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.get('bidi_component')),1)
            self.assertEqual(app.session_state['_live_lab'].root,lab.root)
            self.assertEqual(app.session_state['_live_lab'].bank.account('alice',DEMO_PASSWORD)['balance'],90)
            self.assertEqual(app.session_state['_live_lab'].result['sync']['height'],3)
        other=AppTest.from_file(str(ROOT/'app.py'),default_timeout=40).run()
        self.assertFalse(other.exception)
        self.assertNotEqual(other.session_state['_live_lab'].root,lab.root)
        self.assertEqual(other.session_state['_live_lab'].bank.account('alice',DEMO_PASSWORD)['balance'],100)
