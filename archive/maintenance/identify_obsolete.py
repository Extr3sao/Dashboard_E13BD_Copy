
import re

with open(r"c:\Users\45485456N\OneDrive - Generalitat de Catalunya\.....Antigravity\Dashboard E13BD\src\api\post_crq_audit.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

def_v7_starts = []
for i, line in enumerate(lines):
    if re.search(r"def _build_post_crq_(pdf|markdown)_from_report_model", line):
        if "_v7" in line:
            def_v7_starts.append(i + 1)
        else:
            print(f"Borrable: {i+1}: {line.strip()}")

print(f"V7 starts: {def_v7_starts}")
