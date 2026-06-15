import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.core.oracle_client import ensure_oracle_thick_mode, resolve_oracle_client_lib_dir


class TestOracleClient(unittest.TestCase):
    def test_resolve_oracle_client_lib_dir_prefers_config(self):
        with patch.dict("os.environ", {"ORACLE_CLIENT_LIB_DIR": "env-client"}):
            result = resolve_oracle_client_lib_dir({"ORACLE_CLIENT_LIB_DIR": "config-client"})

        self.assertEqual(result, "config-client")

    @patch("src.core.oracle_client.oracledb")
    def test_ensure_oracle_thick_mode_initializes_existing_client_path(self, oracledb_mock):
        oracledb_mock.is_thin_mode.side_effect = [True, False]

        with TemporaryDirectory() as tmpdir:
            result = ensure_oracle_thick_mode({"ORACLE_CLIENT_LIB_DIR": tmpdir})

        oracledb_mock.init_oracle_client.assert_called_once_with(lib_dir=str(Path(tmpdir).resolve()))
        self.assertEqual(result, str(Path(tmpdir).resolve()))

    @patch("src.core.oracle_client._windows_short_path", return_value="C:/SHORT/INSTAN~1")
    @patch("src.core.oracle_client._is_ascii_path", side_effect=[False, True])
    @patch("src.core.oracle_client.oracledb")
    def test_ensure_oracle_thick_mode_uses_short_path_for_non_ascii_paths(
        self,
        oracledb_mock,
        _is_ascii_path,
        _windows_short_path,
    ):
        oracledb_mock.is_thin_mode.side_effect = [True, False]

        with TemporaryDirectory() as tmpdir:
            result = ensure_oracle_thick_mode({"ORACLE_CLIENT_LIB_DIR": tmpdir})

        oracledb_mock.init_oracle_client.assert_called_once_with(lib_dir="C:/SHORT/INSTAN~1")
        self.assertEqual(result, "C:/SHORT/INSTAN~1")

    @patch("src.core.oracle_client.oracledb")
    def test_ensure_oracle_thick_mode_rejects_missing_client_path(self, oracledb_mock):
        oracledb_mock.is_thin_mode.return_value = True

        with self.assertRaises(RuntimeError) as ctx:
            ensure_oracle_thick_mode({"ORACLE_CLIENT_LIB_DIR": "C:/does/not/exist"})

        self.assertIn("Oracle Thick Mode es obligatori", str(ctx.exception))
        oracledb_mock.init_oracle_client.assert_not_called()

    @patch("src.core.oracle_client.oracledb")
    def test_ensure_oracle_thick_mode_wraps_initialization_error(self, oracledb_mock):
        oracledb_mock.is_thin_mode.return_value = True
        oracledb_mock.init_oracle_client.side_effect = RuntimeError("bad oci")

        with TemporaryDirectory() as tmpdir:
            with self.assertRaises(RuntimeError) as ctx:
                ensure_oracle_thick_mode({"ORACLE_CLIENT_LIB_DIR": tmpdir})

        self.assertIn("No s'ha pogut inicialitzar Oracle Thick Mode", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
