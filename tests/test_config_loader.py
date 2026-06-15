from pathlib import Path

from src.core.config_loader import ConfigLoader


def test_load_connections_parses_profiles_and_comments(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    connections_file = config_dir / "Cadena_conexions.txt"
    connections_file.write_text(
        "# comentari\n\n## E13DB\nUSER = usr\nPASSWORD = pw\nDSN = host/service\n\n## ALTRE\nUSER = alt\nPASSWORD = sec\nDSN = svc\n",
        encoding="utf-8",
    )

    loader = ConfigLoader(str(config_dir))

    profiles = loader.load_connections(str(connections_file))

    assert profiles == {
        "E13DB": {"USER": "usr", "PASSWORD": "pw", "DSN": "host/service"},
        "ALTRE": {"USER": "alt", "PASSWORD": "sec", "DSN": "svc"},
    }


def test_resolve_profile_name_is_tolerant_to_case_and_extra_text(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    loader = ConfigLoader(str(config_dir))
    profiles = {
        "E13 DB Produccio": {"USER": "usr", "PASSWORD": "pw", "DSN": "dsn"},
        "ALTRE": {"USER": "alt", "PASSWORD": "pw", "DSN": "dsn"},
    }

    resolved = loader.resolve_profile_name("  e13 db produccio oracle principal  ", profiles)

    assert resolved == "E13 DB Produccio"


def test_save_connection_upserts_existing_profile_without_duplicates(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("CONNECTIONS_FILE", str(config_dir / "Cadena_conexions.txt"))
    loader = ConfigLoader(str(config_dir))

    assert loader.save_connection("E13DB", "user1", "pw1", "dsn1") is True
    assert loader.save_connection("  e13db  ", "user2", "pw2", "dsn2") is True

    connections_file = config_dir / "Cadena_conexions.txt"
    content = connections_file.read_text(encoding="utf-8")

    assert content.count("## E13DB") == 1
    assert loader.load_connections(str(connections_file)) == {
        "E13DB": {"USER": "user2", "PASSWORD": "pw2", "DSN": "dsn2"}
    }


def test_save_env_var_updates_existing_and_appends_new_value(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    env_path = config_dir / ".env"
    env_path.write_text("OPENROUTER_API_KEY=old\n", encoding="utf-8")
    loader = ConfigLoader(str(config_dir))

    assert loader.save_env_var("OPENROUTER_API_KEY", "new") is True
    assert loader.save_env_var("DEFAULT_PROFILE", "E13DB") is True

    content = env_path.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY=new\n" in content
    assert "DEFAULT_PROFILE=E13DB\n" in content
    assert loader.get_env_var("OPENROUTER_API_KEY") == "new"
    assert loader.get_env_var("DEFAULT_PROFILE") == "E13DB"
