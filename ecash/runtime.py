"""Session-scoped storage for the public teaching demo."""
import re
import secrets
import tempfile
from pathlib import Path

DEMO_PASSWORD = 'DemoCash2026!'


def session_root(state):
    key = state.get('_cash_workspace')
    if not isinstance(key, str) or re.fullmatch(r'[0-9a-f]{64}', key) is None:
        key = secrets.token_hex(32)
        state['_cash_workspace'] = key
    return Path(tempfile.gettempdir()) / 'offline-cash-sessions' / key


def bootstrap(bank):
    if not bank.db.rows('SELECT id FROM settings'):
        bank.initialize()
    names = {x['name'] for x in bank.dashboard()['accounts']}
    for name, kind in [('alice', 'payer'), ('shop_a', 'merchant'), ('shop_b', 'merchant')]:
        if name not in names:
            bank.create_account(name, DEMO_PASSWORD, kind)
