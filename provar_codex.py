import sys
import os

# Afegim el directori actual al path per poder importar core
sys.path.insert(0, os.path.abspath(os.path.curdir))

from core.sql_codex_transformer import transform_for_codex, validate_codex_sql

# --- ENGANXA AQUÍ LA TEVA CONSULTA PER PROVAR ---
consulta_de_prova = """
DEFINE START_AT = '2026-04-01 00:00:00'
-- Consulta d'exemple per provar el transformador
SELECT *
FROM dba_audit_trail
WHERE timestamp > TO_DATE('&START_AT', 'YYYY-MM-DD HH24:MI:SS')
  AND action_name = '&ACCIO';
"""
# -----------------------------------------------

def executar_prova(sql):
    print("="*60)
    print("🔍 CONSULTA ORIGINAL (Oracle SQL Developer)")
    print("="*60)
    print(sql.strip())
    print("\n" + "="*60)
    
    # Transformació en mode debug per veure què ha passat
    resultat = transform_for_codex(sql, debug=True)
    
    print("✨ CONSULTA TRANSFORMADA (Format Codex)")
    print("="*60)
    print(resultat.sql)
    print("\n" + "="*60)
    print("📝 CANVIS APLICATS:")
    for change in resultat.changes:
        print(f"  ✔ {change}")
        
    print("\n✅ VARIABLES DETECTADES PER CODEX:")
    print(f"  {resultat.variables_found}")
    
    # Validació extra
    valida = validate_codex_sql(resultat.sql)
    if not valida['valid']:
        print("\n❌ ERRORS:")
        for err in valida['errors']:
            print(f"  - {err}")

if __name__ == "__main__":
    executar_prova(consulta_de_prova)
    print("\n💡 Consell: Pots editar el fitxer 'provar_codex.py' i canviar la variable 'consulta_de_prova' per provar qualsevol SQL.")
