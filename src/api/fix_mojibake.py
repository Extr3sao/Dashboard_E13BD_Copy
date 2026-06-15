import os

def fix_mojibake(filename):
    with open(filename, 'rb') as f:
        content = f.read()
    
    # We want to go from the multi-encoded mess back to clean UTF-8.
    # Patterns for triple/quadruple encoding common in this file:
    # \xc3\x83\xc6\x92\xc3\x82\xc2\xb3 -> ó (C3 B3)
    # \xc3\x83\xc6\x92\xc3\x82\xc2\xa0 -> à (C3 A0)
    # \xc3\x83\xc6\x92\xc3\x82\xc2\xa8 -> è (C3 A8)
    # \xc3\x83\xc6\x92\xc3\x82\xc2\xa9 -> é (C3 A9)
    # \xc3\x83\xc6\x92\xc3\x82\xc2\xad -> í (C3 AD)
    # \xc3\x83\xc6\x92\xc3\x82\xc2\xb2 -> ò (C3 B2)
    # \xc3\x83\xc6\x92\xc3\x82\xc2\xba -> ú (C3 BA)
    # \xc3\x83\xc6\x92\xc3\x82\xc2\xa7 -> ç (C3 A7)
    
    # Actually, a more general way:
    # If we have bytes that look like UTF-8 but are actually Latin-1 of UTF-8...
    # We can try to decode/encode iteratively.
    
    try:
        # First, let's try to detect if it's already clean UTF-8
        text = content.decode('utf-8')
        # If it contains these "ÃƒÂ" sequences, it's corrupted
        if "ÃƒÂ" in text or "Ã­" in text or "Ã " in text or "Ã©" in text or "Ã²" in text or "Ã³" in text:
            print(f"Detectat mojibake a {filename}, intentant reparar...")
            
            # Manual replacements for the worst ones seen in the file
            # These are specific to the triple-encoding state
            replacements = {
                "ÃƒÂ³": "ó",
                "ÃƒÂ ": "à",
                "ÃƒÂ©": "é",
                "ÃƒÂ¨": "è",
                "ÃƒÂ­": "í",
                "ÃƒÂ¯": "ï",
                "ÃƒÂ²": "ò",
                "ÃƒÂº": "ú",
                "ÃƒÂ¼": "ü",
                "ÃƒÂ§": "ç",
                "ÃƒÂ¡": "á",
                "Ã‚Â·": "·",
                "ÃƒÂ": "à", # Fallback for truncated à
                # Double encoding patterns
                "Ã³": "ó",
                "Ã ": "à",
                "Ã©": "é",
                "Ã¨": "è",
                "Ã­": "í",
                "Ã¯": "ï",
                "Ã²": "ò",
                "Ãº": "ú",
                "Ã¼": "ü",
                "Ã§": "ç",
                "Ã¡": "á",
                "Ã±": "ñ",
                "Â·": "·",
                "Ãˆ": "È",
                "Ã‰": "É",
                "Ã€": "À",
                "Ã’": "Ò",
                "Ã“": "Ó",
            }
            
            for k, v in replacements.items():
                text = text.replace(k, v)
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(text)
            print("Reparació completada.")
        else:
            print(f"{filename} sembla estar correcte.")
    except Exception as e:
        print(f"Error processant {filename}: {e}")

if __name__ == "__main__":
    target = r"C:\Users\45485456N\OneDrive - Generalitat de Catalunya\.....Antigravity\Dashboard E13BD\src\api\post_crq_audit.py"
    fix_mojibake(target)
