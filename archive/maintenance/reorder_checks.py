import re
import os

md_file = 'auditoria_post_crq.md'
txt_file = 'consultes_post_crq.txt'

def reorder():
    if not os.path.exists(md_file) or not os.path.exists(txt_file):
        print("Fitxers no trobats.")
        return

    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()

    with open(txt_file, 'r', encoding='utf-8') as f:
        txt_content = f.read()

    # Busquem tots els CHECK_XX al markdown (que defineix l'ordre)
    matches = re.findall(r'(CHECK_\d+)', md_content)
    
    seen = set()
    ordered_checks = []
    for m in matches:
        if m not in seen:
            ordered_checks.append(m)
            seen.add(m)

    # Creem un mapa antic -> nou
    mapping = {}
    for i, old_check in enumerate(ordered_checks):
        new_check = f'CHECK_{i+1:02d}' # o:02d per afegir zeros si cal (01, 02)
        mapping[old_check] = new_check

    # Apliquem el reemplaçament de llarg a curt per no solapar (ex: CHECK_10 vs CHECK_1)
    new_md = md_content
    new_txt = txt_content
    for old_check, new_check in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
        # Fem servir límits de paraula per assegurar
        new_md = re.sub(rf'\b{old_check}\b', new_check, new_md)
        new_txt = re.sub(rf'\b{old_check}\b', new_check, new_txt)

    # Guardem els fitxers
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(new_md)
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write(new_txt)

    print(f'S\'han reordenat {len(mapping)} checks de forma consecutiva.')
    for old_c, new_c in mapping.items():
        if old_c != new_c:
            print(f'Renomenat: {old_c} -> {new_c}')

if __name__ == "__main__":
    reorder()
