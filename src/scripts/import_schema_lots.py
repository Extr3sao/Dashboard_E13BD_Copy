import pandas as pd
import sqlite3
import os
import sys

def main():
    from src.core.sqlite_paths import resolve_sqlite_path
    from pathlib import Path
    
    # Intentem trobar l'excel de forma relativa si la ruta absoluta falla
    excel_path = r"listado_owner_lot.xlsx"
    if not os.path.exists(excel_path):
        excel_path = r"C:\Users\45485456N\Generalitat de Catalunya\Espai_compartit_EaE - Documents\Eliminació obsolets E13DB\listado_owner_lot.xlsx"
    
    db_path = resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db")

    print(f"Llegint arxiu Excel: {excel_path}")
    
    try:
        # Llegim l'Excel
        df = pd.read_excel(excel_path)
        
        # Comprovem columnes necessàries
        if 'Owner' not in df.columns or 'Lot' not in df.columns:
            print("Error: L'Excel no conté les columnes 'Owner' i 'Lot'.")
            sys.exit(1)
            
        print(f"Files llegides de l'Excel: {len(df)}")
        
        # Tractem dades: netegem espais, nulls a Lot -> "SENSE LOT"
        df['Owner'] = df['Owner'].astype(str).str.strip().str.upper()
        df['Lot'] = df['Lot'].fillna('SENSE LOT').astype(str).str.strip().str.upper()
        
        # Preparem llista per SQLite
        records = list(df[['Owner', 'Lot']].itertuples(index=False, name=None))
        
        # Connectem a SQLite
        print(f"Connectant a la BBDD: {db_path}")
        
        # Assegurem que el directori data existeix
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Creem taula si no existeix
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schema_lots (
                schema_name TEXT PRIMARY KEY,
                lot_name TEXT NOT NULL
            )
        ''')
        
        # Inserim o actualitzem els registres (UPSERT)
        cursor.executemany('''
            INSERT INTO schema_lots (schema_name, lot_name) 
            VALUES (?, ?)
            ON CONFLICT(schema_name) DO UPDATE SET lot_name=excluded.lot_name
        ''', records)
        
        conn.commit()
        print(f"Mapping inserit / actualitzat correctament. Registres totals afectats: {len(records)}.")
        
    except Exception as e:
        print(f"Error durant l'execució: {e}")
        sys.exit(1)
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    main()
