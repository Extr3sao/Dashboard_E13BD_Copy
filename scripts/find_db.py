import os
import sqlite3

def check():
    db_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'OracleAudit', 'checks_repository.db')
    print(f'Checking {db_path}...')
    if os.path.exists(db_path):
        print('Found!')
        # Let's read it with timeout
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        print('Connected!')
        cur.execute("SELECT check_id, actiu FROM audit_checks")
        rows = cur.fetchall()
        print(f'Total {len(rows)} rows.')
        for r in rows:
            print(f" {r['check_id']} actiu={r['actiu']}")
            
if __name__ == '__main__':
    check()
