import sys
import io
from docx import Document

# Forçar UTF-8 a la sortida
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def extract_text(file_path):
    print(f"\n--- CONTINGUT DE: {file_path} ---")
    try:
        doc = Document(file_path)
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                print(text)
    except Exception as e:
        # Si falla l'encoding al print, intentem una forma més segura
        print(f"Error llegint {file_path}: {str(e).encode('ascii', 'ignore').decode()}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Ús: python extract_docx.py <path_al_document>")
    else:
        extract_text(sys.argv[1])
