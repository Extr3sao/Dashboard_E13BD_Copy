
import re
filepath = r"src\api\post_crq_audit.py"
with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.startswith("def "):
        name = line.split("(")[0].replace("def ", "").strip()
        print(f"{i+1}:{name}")
