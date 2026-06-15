import requests
import json

base_url = "http://localhost:8000/api"

# Simulació del que envia el frontend
# Input de l'usuari: 'DUPLIXTEC' , 'E13_ADPD' , 'E13_AFD'
# App.jsx: schemaToAudit.replace(/['"]/g, '').trim() -> DUPLIXTEC , E13_ADPD , E13_AFD
# Després encodeURIComponent(...)
input_raw = "'DUPLIXTEC' , 'E13_ADPD' , 'E13_AFD'"
clean_input_frontend = input_raw.replace("'", "").replace('"', "").strip()
print(f"Frontend clean output: [{clean_input_frontend}]")

url = f"{base_url}/audit/deep-scan/{requests.utils.quote(clean_input_frontend)}"
print(f"Requesting URL: {url}")

res = requests.get(url)
if res.status_code == 200:
    data = res.json()
    print(f"Resultats rebuts: {len(data)}")
    if isinstance(data, list):
        for r in data:
            if isinstance(r, dict):
                print(f"- {r.get('username')} (Score: {r.get('obsolescence_score')}%)")
            else:
                print(f"- Resultat no és dict: {type(r)} -> {r}")
    else:
        print(f"Data no és llista: {type(data)}")
else:
    print(f"Error: {res.status_code} - {res.text}")
