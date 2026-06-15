import os
import re
import shutil
import datetime
from pathlib import Path

def backup_and_reorder_all_checks(deleted_check_id: str):
    project_root = Path(os.getcwd())
    md_file = project_root / 'auditoria_post_crq.md'
    txt_file = project_root / 'consultes_post_crq.txt'
    backup_dir = project_root / 'backup_audits'
    
    deleted_check_id = deleted_check_id.upper()
    
    if not md_file.exists() or not txt_file.exists():
        return False, "Els fitxers principals de la UI no es troben (MD o TXT)."
        
    backup_dir.mkdir(exist_ok=True)
    t = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    shutil.copy2(md_file, backup_dir / f'auditoria_{t}.md')
    shutil.copy2(txt_file, backup_dir / f'consultes_{t}.txt')
    
    with open(txt_file, 'r', encoding='utf-8') as f:
        txt_content = f.read()
        
    all_checks = re.findall(r'(CHECK_\d+)', txt_content, re.IGNORECASE)
    all_checks = [c.upper() for c in all_checks]
    active_checks = []
    
    for c in all_checks:
        if c not in active_checks:
            active_checks.append(c)
            
    if deleted_check_id in active_checks:
        active_checks.remove(deleted_check_id)
        
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()
        
    blocks = re.split(r'(?=###\s+CHECK_\d+)', md_content, flags=re.IGNORECASE)
    filtered_md_blocks = []
    
    for block in blocks:
        match = re.search(r'###\s+(CHECK_\d+)', block, re.IGNORECASE)
        if match:
            c_id = match.group(1).upper()
            if c_id != deleted_check_id:
                filtered_md_blocks.append(block)
        else:
            filtered_md_blocks.append(block)
            
    clean_md_content = ''.join(filtered_md_blocks)
    
    txt_blocks = re.split(r'(?m)^(?=CHECK_\d+\s*\|)', txt_content)
    filtered_txt_blocks = []
    
    for block in txt_blocks:
        match = re.search(r'^(CHECK_\d+)\s*\|', block, re.IGNORECASE)
        if match:
            c_id = match.group(1).upper()
            if c_id != deleted_check_id:
                filtered_txt_blocks.append(block)
        else:
            filtered_txt_blocks.append(block)
            
    clean_txt_content = ''.join(filtered_txt_blocks)

    mapping = {}
    for idx, old_id in enumerate(active_checks, start=1):
        new_id = f'CHECK_{idx:02d}'
        mapping[old_id] = new_id
        
    for old_check, new_check in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
        if old_check != new_check:
            clean_md_content = re.sub(rf'\b{old_check}\b', new_check, clean_md_content)
            clean_txt_content = re.sub(rf'\b{old_check}\b', new_check, clean_txt_content)

    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(clean_md_content)
        
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write(clean_txt_content.strip() + '\n')
        
    return True, f"Backup creat amb èxit. {deleted_check_id} esborrat. Numèrics actualitzats."

if __name__ == '__main__':
    res, msg = backup_and_reorder_all_checks('CHECK_11')
    print(msg)
