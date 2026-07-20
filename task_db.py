import sqlite3
import os
import random
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_code TEXT PRIMARY KEY,
            source_type TEXT,
            source_path_or_url TEXT,
            created_at REAL,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

def create_task(source_type, source_path_or_url):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Generate unique 6-digit code like RUN-4829
    while True:
        code_num = random.randint(1000, 9999)
        task_code = f"RUN-{code_num}"
        cursor.execute("SELECT task_code FROM tasks WHERE task_code=?", (task_code,))
        if not cursor.fetchone():
            break
            
    cursor.execute("""
        INSERT INTO tasks (task_code, source_type, source_path_or_url, created_at, status)
        VALUES (?, ?, ?, ?, ?)
    """, (task_code, source_type, source_path_or_url, time.time(), "PENDING"))
    
    conn.commit()
    conn.close()
    return task_code

def get_task(task_code):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT task_code, source_type, source_path_or_url, status FROM tasks WHERE task_code=?", (task_code.upper().strip(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "task_code": row[0],
            "source_type": row[1],
            "source_path_or_url": row[2],
            "status": row[3]
        }
    return None

def update_task_status(task_code, status):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET status=? WHERE task_code=?", (status, task_code))
    conn.commit()
    conn.close()
