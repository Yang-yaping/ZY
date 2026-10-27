"""Integration regression: page routing must preserve both experiments' state."""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

from ecash.bank import Bank
from ecash.runtime import session_root, DEMO_PASSWORD

PROJECT = Path(__file__).resolve().parents[1]


class NavigationTests(unittest.TestCase):
    def button(self, app, label):
        next(b for b in app.button if b.label==label).click().run()
        self.assertEqual(len(app.exception),0)

    def test_cash_withdrawal_p2p_roundtrip_and_session_isolation(self):
        app = AppTest.from_file(str(PROJECT/'cloud_app.py'),default_timeout=45).run()
        self.assertEqual(len(app.exception),0)
        workspace = app.session_state['_cash_workspace']
        root = session_root({'_cash_workspace':workspace})
        bank = Bank(root/'bank.db')
        app.sidebar.radio[0].set_value('付款人').run()
        app.text_input[0].set_value(DEMO_PASSWORD).run()
        self.button(app,'① 生成候选电子现金并盲化')
        self.button(app,'② 提交盲化值，接收银行随机抽查')
        self.button(app,'③ 回应抽查 → 银行盲签 → 去盲')
        self.assertEqual(bank.account('alice',DEMO_PASSWORD)['balance'],90)
        app.switch_page('p2p/app.py').run()
        self.assertEqual(len(app.exception),0)
        self.button(app,'开始实验')
        result = app.session_state['p2p_result']
        self.assertTrue(result['sync']['success'])
        self.assertEqual(result['sync']['height'],3)
        self.assertEqual(result['discovery']['active'],100)
        self.assertEqual(result['active_after_offline'],95)
        app.switch_page('cash_app.py').run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.sidebar.radio[0].value,'付款人')
        self.assertEqual(app.session_state['_cash_workspace'],workspace)
        self.assertEqual(bank.account('alice',DEMO_PASSWORD)['balance'],90)
        app.switch_page('p2p/app.py').run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.session_state['p2p_result']['sync']['tip'],result['sync']['tip'])
        self.assertEqual(app.session_state['_cash_workspace'],workspace)
        other = AppTest.from_file(str(PROJECT/'cloud_app.py'),default_timeout=45).run()
        self.assertEqual(len(other.exception),0)
        self.assertNotEqual(other.session_state['_cash_workspace'],workspace)
        other_bank=Bank(session_root({'_cash_workspace':other.session_state['_cash_workspace']})/'bank.db')
        self.assertEqual(other_bank.account('alice',DEMO_PASSWORD)['balance'],100)


if __name__ == '__main__':
    unittest.main(verbosity=2)
