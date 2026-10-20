import unittest
from ecash.runtime import session_root


class RuntimeTests(unittest.TestCase):
    def test_workspace_is_stable_within_session(self):
        state = {}
        self.assertEqual(session_root(state), session_root(state))

    def test_visitors_get_distinct_workspaces(self):
        self.assertNotEqual(session_root({}), session_root({}))

    def test_untrusted_workspace_cannot_escape_directory(self):
        state = {'_cash_workspace': '../../someone-else'}
        root = session_root(state)
        self.assertEqual(root.parent.name, 'offline-cash-sessions')
        self.assertEqual(len(root.name), 64)
