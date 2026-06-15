
import re

filepath = r"c:\Users\45485456N\OneDrive - Generalitat de Catalunya\.....Antigravity\Dashboard E13BD\src\api\post_crq_audit.py"

with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

def find_func_end(start_idx):
    for i in range(start_idx + 1, len(lines)):
        if re.match(r"^def [a-zA-Z0-9_]+\(", lines[i]):
            # Peek back to common decorators if any, but we mostly just need to end before next def
            return i
    return len(lines)

to_delete_names = []
with open("to_delete.txt", "r") as f:
    for line in f:
        if ":" in line:
            to_delete_names.append(line.split(":")[1].strip())

to_delete_ranges = []
for i, line in enumerate(lines):
    match = re.match(r"^def (_[a-zA-Z0-9_]+)\(", line)
    if match:
        name = match.group(1)
        if name in to_delete_names:
            end = find_func_end(i)
            # Check if there's a comment before the def that we should also delete? 
            # Usually not necessary for this cleanup
            to_delete_ranges.append((i+1, end, name))

# Sort ranges backwards to delete safely
to_delete_ranges.sort(key=lambda x: x[0], reverse=True)
for r in to_delete_ranges:
    print(f"ReplacementChunk(StartLine={r[0]}, EndLine={r[1]}, TargetContent=\"\"\"...\"\"\", ReplacementContent=\"\"),")
