import sqlite3
import os

# 1. CHANGE THIS to match your ACTUAL file name
filename = "mission_log.sqlite"  # <-- Make sure this matches exactly!

# 2. Check if the file actually exists here
full_path = os.path.abspath(filename)
print(f"Looking for: {full_path}")
print(f"File exists? {os.path.exists(full_path)}")

if os.path.exists(full_path):
    # 3. Check the file size - empty files are usually 0 bytes
    file_size = os.path.getsize(full_path)
    print(f"File size: {file_size} bytes")
    
    if file_size == 0:
        print("❌ The file is completely empty. You never actually wrote data to it.")
    else:
        # 4. Try to open it and list the tables
        try:
            conn = sqlite3.connect(full_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            print(f"✅ Tables found: {tables}")
            
            if not tables:
                print("❌ The file exists but has zero tables. Did your 'CREATE TABLE' code run successfully?")
            conn.close()
        except sqlite3.DatabaseError as e:
            print(f"❌ Corrupt or invalid SQLite file: {e}")
else:
    print("❌ The file isn't in this folder. Double-check the spelling (.sqlite vs .db) and the folder path.")