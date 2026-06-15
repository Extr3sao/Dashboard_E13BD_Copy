import unittest
from unittest.mock import Mock, patch

from src.core.db_manager import OracleDBManager
from src.api.post_crq_audit import _sql_with_binds, parse_post_crq_checks


class _FakeCursor:
    def __init__(self, *, rows=None, description=None, execute_error=None):
        self._rows = rows or []
        self.description = description or [("COL1",)]
        self._execute_error = execute_error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params):
        if self._execute_error:
            raise self._execute_error

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, cursor_obj):
        self._cursor_obj = cursor_obj
        self.closed = False
        self.call_timeout = None

    def cursor(self):
        return self._cursor_obj

    def close(self):
        self.closed = True


class TestOracleDBManager(unittest.TestCase):
    def setUp(self):
        self.thick_mode_patcher = patch("src.core.db_manager.ensure_oracle_thick_mode", return_value=None)
        self.ensure_thick_mode = self.thick_mode_patcher.start()

    def tearDown(self):
        self.thick_mode_patcher.stop()

    def test_execute_query_closes_broken_connection_and_returns_none(self):
        manager = OracleDBManager({"USER": "u", "PASSWORD": "p", "DSN": "dsn"})
        cursor = _FakeCursor(execute_error=RuntimeError("oracle broken"))
        connection = _FakeConnection(cursor)
        manager.connection = connection

        rows, cols = manager.execute_query("select 1 from dual")

        self.assertIsNone(rows)
        self.assertIsNone(cols)
        self.assertTrue(connection.closed)
        self.assertIsNone(manager.connection)
        self.assertEqual(manager.last_error, "oracle broken")

    def test_manager_requires_oracle_thick_mode_on_initialization(self):
        config = {"USER": "u", "PASSWORD": "p", "DSN": "dsn", "ORACLE_CLIENT_LIB_DIR": "C:/oracle/instantclient"}

        OracleDBManager(config)

        self.ensure_thick_mode.assert_called_once_with(config)

    @patch("src.core.db_manager.oracledb.connect")
    def test_execute_query_reconnects_after_previous_failure(self, connect_mock):
        first = _FakeConnection(_FakeCursor(execute_error=RuntimeError("boom")))
        second = _FakeConnection(_FakeCursor(rows=[(1,)], description=[("VALUE",)]))
        connect_mock.side_effect = [first, second]

        manager = OracleDBManager({"USER": "u", "PASSWORD": "p", "DSN": "dsn"})
        rows, cols = manager.execute_query("select 1 from dual")
        self.assertIsNone(rows)
        self.assertIsNone(cols)
        self.assertIsNone(manager.connection)

        rows, cols = manager.execute_query("select 1 from dual")
        self.assertEqual(rows, [(1,)])
        self.assertEqual(cols, ["VALUE"])
        self.assertIs(manager.connection, second)

    def test_close_is_idempotent_and_clears_connection(self):
        manager = OracleDBManager({"USER": "u", "PASSWORD": "p", "DSN": "dsn"})
        connection = Mock()
        manager.connection = connection

        manager.close()
        manager.close()

        connection.close.assert_called_once()
        self.assertIsNone(manager.connection)

    def test_filter_params_for_query_ignores_comments_with_apostrophes_in_check_03(self):
        check = next(item for item in parse_post_crq_checks() if item["check_id"] == "CHECK_03")
        sql = _sql_with_binds(check["sql"])

        params = {
            "START_DATE": "2026-03-24",
            "start_date": "2026-03-24",
            "END_DATE": "2026-03-25",
            "end_date": "2026-03-25",
            "DAYS_BACK": 1,
            "days_back": 1,
        }

        safe = OracleDBManager._filter_params_for_query(sql, params)

        self.assertEqual(safe["start_date"], "2026-03-24")
        self.assertEqual(safe["end_date"], "2026-03-25")
        self.assertNotIn("MI", safe)

    def test_filter_params_for_query_ignores_comments_with_apostrophes_in_check_06(self):
        check = next(item for item in parse_post_crq_checks() if item["check_id"] == "CHECK_06")
        sql = _sql_with_binds(check["sql"])

        params = {
            "START_DATE": "2026-03-24",
            "start_date": "2026-03-24",
            "END_DATE": "2026-03-25",
            "end_date": "2026-03-25",
            "DAYS_BACK": 1,
            "days_back": 1,
        }

        safe = OracleDBManager._filter_params_for_query(sql, params)

        self.assertEqual(safe["start_date"], "2026-03-24")
        self.assertEqual(safe["end_date"], "2026-03-25")
        self.assertNotIn("MI", safe)


if __name__ == "__main__":
    unittest.main()
