import os
import sys

import oracledb

# Afegir src al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src.core.config_loader import ConfigLoader
from src.core.oracle_client import ensure_oracle_thick_mode


def test_thick_mode():
    print("--- Diagnostic de Connexio Oracle ---")

    cl = ConfigLoader()
    profile_name = cl.get_env_var("DEFAULT_PROFILE", "E13DB")
    profile = cl.get_profile(profile_name)

    if not profile:
        print(f"ERROR: No s'ha trobat el perfil {profile_name}")
        return

    print(f"Intentant usar Instant Client a: {profile.get('ORACLE_CLIENT_LIB_DIR') or './instantclient'}")

    try:
        ensure_oracle_thick_mode(profile)
        print("SUCCESS: Oracle Thick Mode inicialitzat correctament.")
    except Exception as e:
        print(f"ERROR Thick Mode: {e}")
        return

    try:
        print(f"Connectant a {profile['DSN']} amb usuari {profile['USER']}...")
        conn = oracledb.connect(
            user=profile["USER"],
            password=profile["PASSWORD"],
            dsn=profile["DSN"],
        )
        print("OK: CONNEXIO ESTABLERTA AMB EXIT!")

        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM v$version")
            res = cursor.fetchone()
            print(f"Versio BBDD: {res[0]}")

        conn.close()
    except Exception as e:
        print(f"FAIL: ERROR DE CONNEXIO: {str(e).encode('ascii', 'ignore').decode()}")


if __name__ == "__main__":
    test_thick_mode()
