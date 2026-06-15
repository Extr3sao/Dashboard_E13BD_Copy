import requests
import json
import sys
import os

# Afegir el directori arrel al path per importar mòduls
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.ai_assistant import AIAssistant
from src.core.config_loader import ConfigLoader

def test_api_endpoints():
    print("\n--- TEST ENDPOINTS API ---")
    base_url = "http://localhost:8000/api"
    
    # 1. Test Config (Model List)
    print("1. Verificant llista de models a /config...")
    try:
        res = requests.get(f"{base_url}/config")
        if res.status_code == 200:
            data = res.json()
            models = data.get("available_models", [])
            print(f"[OK] Models trobats: {len(models)}")
            if len(models) > 1:
                print(f"[OK] Seleccio multiple habilitada: {models[:3]}...")
            else:
                print(f"[ERROR] Només hi ha 1 model: {models}")
        else:
            print(f"[ERROR] Status {res.status_code}")
    except Exception as e:
        print(f"[ERROR] No s'ha pogut connectar al backend: {e}")

    # 2. Test Deep Scan Route (Fixing 404)
    print("\n2. Verificant ruta Deep Scan (evitant 404)...")
    try:
        # Provem amb username
        res = requests.get(f"{base_url}/audit/deep-scan/MGR_APP")
        if res.status_code == 200:
            print("[OK] /audit/deep-scan/{username} respon correctament.")
        else:
            print(f"[ERROR] Status {res.status_code}")
            
        # Provem sense username (directori arrel del scan)
        res = requests.get(f"{base_url}/audit/deep-scan/")
        if res.status_code == 200:
            print("[OK] /audit/deep-scan/ (fallback) respon correctament.")
        else:
            print(f"[ERROR] Fallback status {res.status_code}")
    except Exception as e:
        print(f"[ERROR] Deep scan route failed: {e}")

    # 3. Test Deep Scan Complex Input (Regression for special chars)
    print("\n3. Verificant Deep Scan amb caracters especials (cometes/comes)...")
    try:
        # Cridem amb una cadena tipus 'ADSL','MGR_APP'
        # Nota: el backend ho hauria de netejar i agafar ADSL
        complex_input = "'ADSL','MGR_APP'"
        res = requests.get(f"{base_url}/audit/deep-scan/{complex_input}")
        if res.status_code == 200:
            print("[OK] Deep Scan accepta inputs complexos sense 404.")
        else:
            print(f"[ERROR] Status {res.status_code} per input complex.")
    except Exception as e:
        print(f"[ERROR] {e}")

    # 4. Test Bulk Deep Scan (Múltiples esquemes)
    print("\n4. Verificant Bulk Deep Scan (llista d'esquemes)...")
    try:
        bulk_input = "MGR_APP,CORE_DB"
        res = requests.get(f"{base_url}/audit/deep-scan/{bulk_input}")
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) >= 1:
                print(f"[OK] Bulk Deep Scan ha retornat {len(data)} resultats correctament.")
            else:
                print(f"[ERROR] S'esperava una llista de resultats, s'ha rebut: {type(data)}")
        else:
            print(f"[ERROR] Status {res.status_code} per bulk input.")
    except Exception as e:
        print(f"[ERROR] Bulk deep scan test failed: {e}")

def test_ai_resilience():
    print("\n--- TEST RESILIENCIA IA ---")
    config = ConfigLoader()
    key = config.get_env_var("OPENROUTER_API_KEY")
    if not key:
        print("[SKIP] Saltant test IA: Falta OPENROUTER_API_KEY")
        return

    assistant = AIAssistant()
    print("Provant generacio amb fallbacks automatics...")
    try:
        response = assistant.generate_response("Hola, ets un expert DBA?")
        if "DBA" in response or "si" in response.lower() or "oracle" in response.lower():
            print("[OK] L'assistent respon correctament.")
            print(f"Resposta curta: {response[:50]}...")
        else:
            print(f"[WARN] Resposta inesperada: {response[:100]}")
    except Exception as e:
        print(f"[ERROR] en el motor d'IA: {e}")

if __name__ == "__main__":
    test_api_endpoints()
    test_ai_resilience()
