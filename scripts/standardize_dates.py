import sqlite3
import re
import os

DB_PATH = "internal.db"

# Format standardized:
# TO_DATE(&START_AT, 'YYYY-MM-DD HH24:MI:SS')
# TO_DATE(&END_AT,   'YYYY-MM-DD HH24:MI:SS')

def update_queries():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, sql_text FROM checks")
    rows = cursor.fetchall()
    
    updated_count = 0
    
    # regex matches to handle various formats of START_DATE, START_DT, START_AT
    # also with or without quotes
    
    re_start = re.compile(r"(?:TO_DATE\s*\(\s*)?['\"]?&START_(?:DATE|AT|DT)['\"]?\s*(?:,\s*['\"]?[^'\")]*['\"]?\s*)?\)?", re.IGNORECASE)
    re_end = re.compile(r"(?:TO_DATE\s*\(\s*)?['\"]?&END_(?:DATE|AT|DT)['\"]?\s*(?:,\s*['\"]?[^'\")]*['\"]?\s*)?\)?", re.IGNORECASE)

    for row in rows:
        sql = row['sql_text']
        if not sql: continue
        
        original_sql = sql
        
        # Standard replacement
        sql = re_start.sub("TO_DATE(&START_AT, 'YYYY-MM-DD HH24:MI:SS')", sql)
        sql = re_end.sub("TO_DATE(&END_AT,   'YYYY-MM-DD HH24:MI:SS')", sql)
        
        if sql != original_sql:
            cursor.execute("UPDATE checks SET sql_text = ? WHERE id = ?", (sql, row['id']))
            updated_count += 1
            print(f"Updated check {row['id']}")

    conn.commit()
    conn.close()
    print(f"Total updated: {updated_count}")

if __name__ == "__main__":
    update_queries()
