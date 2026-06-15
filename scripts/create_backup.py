import os
import zipfile
import datetime

def create_zip_backup(source_dir, output_filename, excludes):
    print(f"Iniciant backup de {source_dir} a {output_filename}...")
    count = 0
    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            # Filtrar directoris
            dirs[:] = [d for d in dirs if d not in excludes and not d.startswith('.git')]
            
            for file in files:
                # Filtrar fitxers per extensió o nom
                if file == output_filename or file.endswith('.zip'):
                    continue
                
                file_path = os.path.join(root, file)
                # Calcular el camí relatiu per al ZIP
                arcname = os.path.relpath(file_path, source_dir)
                
                # Check for other excludes in the path
                is_excluded = False
                for ex in excludes:
                    if f"{os.sep}{ex}{os.sep}" in f"{os.sep}{arcname}{os.sep}":
                        is_excluded = True
                        break
                
                if not is_excluded:
                    zipf.write(file_path, arcname)
                    count += 1
                    if count % 100 == 0:
                        print(f"Afegits {count} fitxers...")

    print(f"Backup completat! Total fitxers: {count}")

if __name__ == "__main__":
    BASE_DIR = r"c:\Users\45485456N\OneDrive - Generalitat de Catalunya\.....Antigravity\Dashboard E13BD"
    DATE_STR = datetime.datetime.now().strftime("%Y-%m-%d")
    OUTPUT_NAME = f"dashboard_e13bd_backup_{DATE_STR}.zip"
    OUTPUT_PATH = os.path.join(BASE_DIR, OUTPUT_NAME)
    
    EXCLUDES = [
        'node_modules',
        '.venv',
        'venv',
        '__pycache__',
        '.pytest_cache',
        '.agent',
        '.playwright-cli',
        '.gemini',
        'tmp',
        'logs',
        'instantclient' # Sovint pesat i re-descarregable
    ]
    
    create_zip_backup(BASE_DIR, OUTPUT_PATH, EXCLUDES)
