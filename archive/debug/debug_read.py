import os

path = "\\\\?\\" + os.path.abspath(r"src\api\main.py")
print(f"Checking path: {path}")
print(f"Exists: {os.path.exists(path)}")

try:
    with open(path, 'rb') as f:
        content = f.read(100)
        print(f"Successfully read first 100 bytes: {content}")
except Exception as e:
    print(f"Error reading file: {e}")
