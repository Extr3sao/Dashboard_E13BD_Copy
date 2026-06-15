import sys
import os
import requests
import json
from src.core.config_loader import ConfigLoader

def test_openrouter():
    config = ConfigLoader()
    api_key = config.get_env_var("OPENROUTER_API_KEY")
    
    if not api_key:
        print("Error: OPENROUTER_API_KEY no trobada al .env")
        return False
        
    print(f"Provant clau d'API (comenca per {api_key[:10]}...)")
    
    models_to_test = [
        "openai/gpt-oss-120b:free",
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "openrouter/free",
    ]
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    results = {}
    
    for model in models_to_test:
        print(f" Provant model: {model}...", end="", flush=True)
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Hola, respon amb 'OK'"}]
        }
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                data=json.dumps(payload),
                timeout=10
            )
            if response.status_code == 200:
                print(" OK")
                results[model] = "OK"
            elif response.status_code == 429:
                print(f" RATE LIMIT (429)")
                results[model] = "429"
            else:
                print(f" ERROR {response.status_code}: {response.text}")
                results[model] = f"Error {response.status_code}"
        except Exception as e:
            print(f" EXCEPCIO: {e}")
            results[model] = "Exception"
            
    print("\n--- RESUM DE PROVES ---")
    for m, res in results.items():
        print(f"{m:50}: {res}")
        
    # Recomanar el primer disponible
    available = [m for m, res in results.items() if res == "OK"]
    if available:
        print(f"\nRecomanacio: Usa {available[0]}")
        return available[0]
    else:
        print("\nCap model gratuit disponible en aquest moment.")
        return None

if __name__ == "__main__":
    # Necesitem el PYTHONPATH configurat per importar src
    sys.path.append(os.getcwd())
    test_openrouter()
