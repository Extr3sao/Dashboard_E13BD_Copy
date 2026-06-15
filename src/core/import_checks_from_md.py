import sqlite3
import re
import os
from pathlib import Path
from datetime import datetime

# Configuració de rutes (ajustades a l'entorn de l'usuari)
BASE_DIR = Path(r"c:\Users\45485456N\OneDrive - Generalitat de Catalunya\.....Antigravity\Dashboard E13BD")
DB_PATH = BASE_DIR / "src" / "db" / "internal.db"
MD_PATH = BASE_DIR / "auditoria_post_crq.md"
TXT_PATH = BASE_DIR / "consultes_post_crq.txt"

def parse_md_explanations(md_content):
    """Extrau les explicacions de cada check del fitxer .md"""
    explanations = {}
    # Busca seccions "### CHECK_XX:"
    pattern = re.compile(r"### (CHECK_\d+):.*?\n(.*?)(?=\n### CHECK_|\n## |$)", re.DOTALL)
    for match in pattern.finditer(md_content):
        check_id = match.group(1)
        content = match.group(2).strip()
        explanations[check_id] = content
    return explanations

def parse_txt_queries(txt_content):
    """Extrau les consultes SQL de cada check del fitxer .txt"""
    queries = {}
    # Busca blocs "[CHECK_XX]" i el seu contingut fins al següent bloc o final
    pattern = re.compile(r"\[(CHECK_\d+)\]\n(.*?)(?=\n\[CHECK_|\Z)", re.DOTALL)
    for match in pattern.finditer(txt_content):
        check_id = match.group(1)
        sql = match.group(2).strip()
        queries[check_id] = sql
    return queries

def run_migration():
    if not DB_PATH.exists():
        print(f"Error: No s'ha trobat la base de dades a {DB_PATH}")
        return

    if not MD_PATH.exists():
        print(f"Warning: No s'ha trobat {MD_PATH}")
        md_content = ""
    else:
        with open(MD_PATH, 'r', encoding='utf-8') as f:
            md_content = f.read()

    if not TXT_PATH.exists():
        print(f"Warning: No s'ha trobat {TXT_PATH}")
        txt_content = ""
    else:
        with open(TXT_PATH, 'r', encoding='utf-8') as f:
            txt_content = f.read()

    explanations = parse_md_explanations(md_content)
    queries = parse_txt_queries(txt_content)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Per cada check trobat en el TXT (que és la font de les consultes)
    for check_id, sql in queries.items():
        expl = explanations.get(check_id, "Pendent de generació per IA.")
        
        # Determinar tipus (heurística simple)
        tipo = "PLSQL" if any(x in sql.upper() for x in ["BEGIN", "DECLARE", "PROCEDURE", "FUNCTION"]) else "SQL"
        
        # Determinar severitat (per defecte CRITIC si és dels primers, sinó ALTA)
        num = int(check_id.split('_')[1])
        severitat = "CRITIC" if num <= 5 else "ALTA"
        
        # Inserir o Actualitzar Check
        cursor.execute("""
            INSERT INTO audit_checks (check_id, titol, descripcio, severitat, tipus, actiu)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(check_id) DO UPDATE SET
                tipus = excluded.tipus
        """, (check_id, f"Check Automàtic {check_id}", f"Descripció importada per a {check_id}", severitat, tipo))

        # Inserir Versió Inicial de Consulta
        cursor.execute("""
            INSERT INTO consulta_versions (check_id, sql_query, versio, comentari)
            VALUES (?, ?, 1, 'Importació inicial des de fitxer .txt')
            ON CONFLICT DO NOTHING
        """, (check_id, sql))

        # Inserir Explicació Inicial
        cursor.execute("""
            INSERT INTO explicacions (check_id, contingut_markdown, model_ia)
            VALUES (?, ?, 'IMPORT_MANUAL')
            ON CONFLICT(check_id) DO UPDATE SET
                contingut_markdown = excluded.contingut_markdown
        """, (check_id, expl))

        # Registrar Sincronització (ja que venim dels fitxers)
        cursor.execute("""
            INSERT INTO sincronitzacio_fitxers (check_id, darrer_sync_md, darrer_sync_txt, hash_contingut)
            VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'INITIAL_IMPORT')
            ON CONFLICT(check_id) DO NOTHING
        """, (check_id,))

    conn.commit()
    print(f"Migració completada: {len(queries)} checks processats.")
    conn.close()

if __name__ == "__main__":
    run_migration()
