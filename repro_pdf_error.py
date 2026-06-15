import os
import io
import sys
from pathlib import Path
from reportlab.platypus import Paragraph, SimpleDocTemplate
from reportlab.lib.styles import getSampleStyleSheet
import html

# Mocking _fix_encoding and _safe_xml
def _fix_encoding(text):
    if not isinstance(text, str): return text
    return text # Simplified

def _safe_xml(value):
    if not value: return "-"
    text = str(value)
    escaped = html.escape(text, quote=True)
    result = []
    for c in escaped:
        o = ord(c)
        if o < 32:
            if o in (10, 13): result.append(c)
            elif o == 9: result.append("    ")
            else: continue
        elif o < 128: result.append(c)
        else: result.append(f"&#{o};")
    return "".join(result)

# Import the actual catalog loader if possible, or just parse the file
def load_catalog():
    # We'll use the file content we know
    path = Path("EXPLICACION_CHECKS_CONTROL_QUALITAT_CRQ.md")
    content = path.read_text(encoding="utf-8")
    import re
    blocks = re.split(r"^##\s+CHECK_", content, flags=re.MULTILINE)
    catalog = {}
    for block in blocks[1:]:
        lines = block.splitlines()
        check_id = "CHECK_" + lines[0].split(" ")[0].strip(" —-")
        catalog[check_id] = block
    return catalog

def test_check(check_id, content):
    print(f"Testing {check_id}...")
    styles = getSampleStyleSheet()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer)
    story = []
    
    # Simulate the failing Paragraph structure
    try:
        story.append(Paragraph(f"<b>Què detecta:</b> {_safe_xml(content)}", styles["Normal"]))
        doc.build(story)
        print(f"  {check_id}: OK")
    except Exception as e:
        print(f"  {check_id}: FAILED with {e}")

if __name__ == "__main__":
    # We need to extract the specific fields like 'que_detecta'
    # For simplicity, we'll just test the whole block content for each check
    # since _safe_xml is applied to each field separately.
    catalog = load_catalog()
    for cid, content in catalog.items():
        # The actual code splits by ###
        parts = content.split("###")
        for part in parts:
            if part.strip():
                test_check(cid, part.strip())
