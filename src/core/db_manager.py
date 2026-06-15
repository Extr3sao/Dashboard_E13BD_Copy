import logging
import re

import oracledb

from src.core.oracle_client import ensure_oracle_thick_mode


class OracleDBManager:
    def __init__(self, config):
        self.config = config
        self.connection = None
        self.last_error = None
        self._connect_failed = False
        self.logger = logging.getLogger(__name__)

        thick_lib_dir = ensure_oracle_thick_mode(config)
        if thick_lib_dir:
            self.logger.info("Oracle Thick Mode inicialitzat des de: %s", thick_lib_dir)

    def connect(self):
        """Estableix la connexio amb la base de dades."""
        if self._connect_failed:
            return False

        try:
            user = self.config.get("USER")
            password = self.config.get("PASSWORD")
            dsn = self.config.get("DSN")

            if not all([user, password, dsn]):
                raise ValueError("Falten parametres de connexio (USER, PASSWORD, DSN).")

            self.connection = oracledb.connect(
                user=user,
                password=password,
                dsn=dsn,
            )
            timeout_ms = self.config.get("CALL_TIMEOUT_MS")
            if timeout_ms:
                try:
                    self.connection.call_timeout = int(timeout_ms)
                except (AttributeError, TypeError, ValueError):
                    self.logger.warning("No s'ha pogut aplicar CALL_TIMEOUT_MS=%s", timeout_ms)
            self.last_error = None
            self._connect_failed = False
            self.logger.info("Connexio establerta correctament.")
            return True
        except (oracledb.Error, RuntimeError, ValueError) as e:
            self.last_error = str(e)
            self._connect_failed = True
            self.logger.error("Error en connectar a Oracle: %s", e)
            return False

    def execute_query(self, query, params=None):
        """Executa una consulta SQL i retorna els resultats i les capcaleres."""
        if not self.connection:
            if not self.connect():
                return None, None

        try:
            with self.connection.cursor() as cursor:
                safe_params = self._filter_params_for_query(query, params)
                cursor.execute(query, safe_params)
                columns = [col[0] for col in cursor.description]
                data = cursor.fetchall()
                self.last_error = None
                return data, columns
        except (oracledb.Error, RuntimeError, TypeError, ValueError) as e:
            self.last_error = str(e)
            self.logger.error("Error executant consulta: %s", e)
            self.close()
            return None, None

    @staticmethod
    def _strip_sql_comments(query: str) -> str:
        """Elimina comentaris SQL per evitar apostrofs i placeholders falsos en la deteccio de binds."""
        if not query:
            return ""
        without_block = re.sub(r"/\*.*?\*/", " ", query, flags=re.DOTALL)
        return re.sub(r"--.*?$", " ", without_block, flags=re.MULTILINE)

    @staticmethod
    def _strip_string_literals(query: str) -> str:
        """Elimina el contingut de strings literals SQL ('...') per evitar falsos positius."""
        return re.sub(r"'[^']*'", "''", query or "")

    @staticmethod
    def _filter_params_for_query(query, params):
        if not params:
            return {}

        uncommented_query = OracleDBManager._strip_sql_comments(query or "")
        clean_query = OracleDBManager._strip_string_literals(uncommented_query)

        query_binds = re.findall(r":([A-Za-z_][A-Za-z0-9_]*)", clean_query)
        normalized_query_binds = {name.lower(): name for name in query_binds}

        if not normalized_query_binds:
            return {}

        safe_params = {}
        normalized_user_params = {k.lower(): (k, v) for k, v in params.items()}

        for norm_bind, original_bind_name in normalized_query_binds.items():
            if norm_bind in normalized_user_params:
                _, value = normalized_user_params[norm_bind]
                safe_params[original_bind_name] = value

        return safe_params

    def close(self):
        """Tanca la connexio."""
        if self.connection:
            try:
                self.connection.close()
                self.logger.info("Connexio tancada.")
            finally:
                self.connection = None
