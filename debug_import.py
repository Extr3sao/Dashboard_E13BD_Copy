import sys
import os

print(f"Current working directory: {os.getcwd()}")
print(f"Python version: {sys.version}")

try:
    import src.api.main
    print("SUCCESS: src.api.main imported successfully")
except Exception as e:
    print(f"FAILURE: Could not import src.api.main")
    import traceback
    traceback.print_exc()
