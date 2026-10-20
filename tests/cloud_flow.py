"""Check the public entrypoint and isolation of two real Streamlit sessions."""
import os
import sys
from pathlib import Path
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ecash.bank import Bank

os.environ.pop('ECASH_DATA', None)
# The already deployed app.py entrypoint must have the same isolation defaults.
first = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
second = AppTest.from_file(str(ROOT / 'cloud_app.py'), default_timeout=30).run()
assert not first.exception and not second.exception
key = first.session_state['_cash_workspace']
assert key != second.session_state['_cash_workspace']
first.sidebar.radio[0].set_value('付款人').run()
first.text_input[0].set_value('DemoCash2026!').run()
assert not first.exception
next(x for x in first.button if x.label == '① 生成候选电子现金并盲化').click().run()
next(x for x in first.button if x.label == '② 提交盲化值，接收银行随机抽查').click().run()
next(x for x in first.button if x.label == '③ 回应抽查 → 银行盲签 → 去盲').click().run()
assert not first.exception
assert first.session_state['_cash_workspace'] == key
from ecash.runtime import session_root
first_root = session_root({'_cash_workspace': key})
second_root = session_root({'_cash_workspace': second.session_state['_cash_workspace']})
assert Bank(first_root/'bank.db').account('alice', 'DemoCash2026!')['balance'] == 90
assert Bank(second_root/'bank.db').account('alice', 'DemoCash2026!')['balance'] == 100
print('PASS cloud entrypoint, automatic demo accounts, withdrawal and visitor isolation')
