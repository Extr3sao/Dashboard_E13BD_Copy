import requests
import json

def test_dashboard_api():
    url = "http://localhost:8000/api/audit/dashboard-stats"
    payload = ["DUPLIXTEC", "E13_ADPD", "E13_AFD"]
    
    print(f"Testing URL: {url}")
    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("API Response Structure:")
            print(json.dumps(data, indent=2))
            
            # Verificacions
            keys = ["total_gb", "recovered_gb", "distribution", "status_counts", "apex_total", "top_candidates"]
            all_keys = all(k in data for k in keys)
            print(f"\nAll expected keys present: {all_keys}")
            
            if all_keys:
                print("Verification SUCCESS")
            else:
                print("Verification FAILED: Missing keys")
        else:
            print(f"Verification FAILED: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_dashboard_api()
