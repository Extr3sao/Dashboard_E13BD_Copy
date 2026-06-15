import os
import sys
import datetime
import re
import shutil
import sqlite3

sys.path.append('src')
from core.sqlite_paths import resolve_sqlite_path

def clean_and_reorder():
    md_file = 'auditoria_post_crq.md'
    txt_file = 'consultes_post_crq.txt'
    
    db_file = resolve_sqlite_path('AUDIT_DB_PATH', 'checks_repository.db')
    backup_dir = 'backup_audits'

    print(f'➜ SQLite Path: {db_file}')

    # 1. Fer els backups de seguretat
    os.makedirs(backup_dir, exist_ok=True)
    t = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_md = os.path.join(backup_dir, f'auditoria_{t}.md')
    backup_txt = os.path.join(backup_dir, f'consultes_{t}.txt')
    backup_db = os.path.join(backup_dir, f'db_{t}.db')
    
    if os.path.exists(md_file): shutil.copy2(md_file, backup_md)
    if os.path.exists(txt_file): shutil.copy2(txt_file, backup_txt)
    shutil.copy2(db_file, backup_db)
    print(f'➜ Backups desats a: {backup_dir}')

    # 2. Hard-delete dels soft-deleted (actiu=0) a la DB
    conn = sqlite3.connect(db_file, timeout=15)
    cur = conn.cursor()

    cur.execute("SELECT check_id FROM audit_checks WHERE actiu = 0")
    deleted_checks = [r[0] for r in cur.fetchall()]
    
    if deleted_checks:
        print(f'➜ Eliminant permanentment del SQLite: {deleted_checks}')
        cur.execute("DELETE FROM audit_checks WHERE actiu = 0")
        cur.execute("DELETE FROM consulta_versions WHERE check_id NOT IN (SELECT check_id FROM audit_checks)")
        conn.commit()

    # 3. Fer el mapping dels CHECKS actius cap a numeració contínua
    cur.execute("SELECT check_id FROM audit_checks ORDER BY check_id ASC")
    active_checks = [r[0] for r in cur.fetchall()]
    
    mapping = {}
    for i, old_id in enumerate(active_checks, start=1):
        new_id = f'CHECK_{i:02d}'
        if old_id != new_id:
            mapping[old_id] = new_id

    if not mapping and not deleted_checks:
        print('➜ Cap canvi necessari. Els números ja són consecutius i no hi ha esborrats pendents.')
        conn.close()
        return

    # Aplicar els canvis de nomència a la BBDD usant noms '_TMP' per evitar col·lisions de PRIMARY KEY
    if mapping:
        for old_id, new_id in mapping.items():
            cur.execute("UPDATE audit_checks SET check_id = ? WHERE check_id = ?", (new_id + "_TMP", old_id))
            cur.execute("UPDATE consulta_versions SET check_id = ? WHERE check_id = ?", (new_id + "_TMP", old_id))
        for old_id, new_id in mapping.items():
            cur.execute("UPDATE audit_checks SET check_id = ? WHERE check_id = ?", (new_id, new_id + "_TMP"))
            cur.execute("UPDATE consulta_versions SET check_id = ? WHERE check_id = ?", (new_id, new_id + "_TMP"))
        conn.commit()
    conn.close()

    new_active_checks = set([mapping.get(c, c) for c in active_checks])

    # 4. Filtrar i reanomenar MD
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    blocks = re.split(r'(?=###\s+CHECK_\d+)', md_content, flags=re.IGNORECASE)
    filtered_md = []
    
    for block in blocks:
        match = re.search(r'###\s+(CHECK_\d+)', block, re.IGNORECASE)
        if match:
            c_id = match.group(1).upper()
            if c_id in deleted_checks:
                continue
            filtered_md.append(block)
        else:
            filtered_md.append(block)
            
    clean_md_content = ''.join(filtered_md)
    
    # 5. Filtrar i reanomenar TXT
    with open(txt_file, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
        
    filtered_txt = []
    for line in txt_lines:
        match = re.search(r'(CHECK_\d+)', line, re.IGNORECASE)
        if match:
            c_id = match.group(1).upper()
            if c_id in deleted_checks:
                continue
            filtered_txt.append(line)
        else:
            filtered_txt.append(line)
            
    clean_txt_content = ''.join(filtered_txt)

    # Aplicar el string replacement per mapping al MD i TXT
    for old_check, new_check in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
        clean_md_content = re.sub(rf'\b{old_check}\b', new_check, clean_md_content)
        clean_txt_content = re.sub(rf'\b{old_check}\b', new_check, clean_txt_content)
        print(f'🔄 Reanomenant: {old_check} 👉 {new_check}')

    # Desar als fitxers
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(clean_md_content)
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write(clean_txt_content)

    print('\n✅ Base de dades, fitxer Markdown i fitxer TXT resincronitzats correctament i netejats.')

if __name__ == '__main__':
    clean_and_reorder()
