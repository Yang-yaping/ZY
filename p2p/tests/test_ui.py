"""Run Streamlit's own app harness through the interactive workflow."""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


class UITests(unittest.TestCase):
    def test_normal_run_and_metrics(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        self.assertEqual(len(app.exception),0)
        app.button[0].click().run()
        self.assertEqual(len(app.exception),0)
        result = app.session_state['p2p_result']
        self.assertEqual(result['sync']['height'],3)
        self.assertEqual(result['discovery']['active'],100)
        self.assertEqual(result['active_after_offline'],95)
        self.assertTrue(any('同步完成' in item.value for item in app.success))

    def test_disconnect_run_and_event_display(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.selectbox[2].select('disconnect').run()
        app.button[0].click().run()
        self.assertEqual(len(app.exception),0)
        result = app.session_state['p2p_result']
        self.assertEqual(result['profile'],'disconnect')
        self.assertTrue(result['sync']['success'])
        self.assertGreater(result['sync']['disconnects'],0)
        self.assertTrue(result['events'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
