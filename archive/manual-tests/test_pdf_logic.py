from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph
import html
import sys

def test_paragraph(text):
    styles = getSampleStyleSheet()
    try:
        Paragraph(text, styles["BodyText"])
        return True, ""
    except Exception as e:
        return False, str(e)

def _fix_encoding(text):
    if not text: return ""
    return str(text).encode('utf-8', errors='replace').decode('utf-8')

# Simulating the catalog data
catalog_data = [
    {"check_id": "CHECK_01", "que_detecta": "Detecta si hi ha objectes sense grant."},
    # ... I should load the real catalog if possible
]

# But the most important part is testing labels with values
checks_to_test = [
    "Criticitat", "Temps d'execució", "Què detecta", "Per què és important", 
    "Impacte sobre el lot", "Com s'ha de revisar", "Com es pot corregir", 
    "Limitacions o falsos positius", "Validació posterior"
]

def run_tests():
    print("Iniciant tests de Paragraph...")
    
    # Test typical structure in the code
    test_cases = [
        ("<b>Criticitat:</b> Baixa", "Línia estàndard amb etiqueta tancada (Correcte)"),
        ("<b>Criticitat:</b> Baixa</b>", "Línia amb doble tancament (ERROR esperado)"),
        ("<b>Criticitat: Baixa", "Línia sense tancament (ERROR esperado)"),
    ]
    
    for text, desc in test_cases:
        ok, err = test_paragraph(text)
        print(f"Test: {desc}")
        print(f"  Resultat: {'PASS' if ok else 'FAIL'}")
        if not ok:
            print(f"  Error: {err}")
    
    print("\nProvant casos reals del codi actual...")
    # Based on my fixes:
    real_cases = [
        f"<b>Criticitat:</b> {html.escape(_fix_encoding('Baix'))}", # Should be PASS now
    ]
    
    for text in real_cases:
        ok, err = test_paragraph(text)
        print(f"Cas: {text}")
        print(f"  Resultat: {'PASS' if ok else 'FAIL'}")
        if not ok:
            print(f"  Error: {err}")

if __name__ == "__main__":
    run_tests()
