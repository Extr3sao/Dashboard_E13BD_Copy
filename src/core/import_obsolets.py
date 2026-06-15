import re
import os
from src.core.internal_db import InternalDBManager

def import_obsolets(file_path="resources/neteja_obsolets.txt"):
    if not os.path.exists(file_path):
        print(f"Fitxer no trobat: {file_path}")
        return

    db = InternalDBManager()
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Separem per seccions basades en --##
    sections = re.split(r'(--## .*)\n', content)
    
    current_title = "General"
    for i in range(1, len(sections), 2):
        title = sections[i].replace("--##", "").strip()
        sql_block = sections[i+1].strip()
        
        if sql_block:
            # Netegem el SQL si té comentaris inicials
            db.add_query(
                sql_text=sql_block,
                explanation=f"Consulta experta: {title}",
                source="IMPORTED",
                tags=["obsolets", "auditoria"]
            )
            print(f"Importada: {title}")

if __name__ == "__main__":
    import_obsolets()
