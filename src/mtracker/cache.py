import sqlite3
import json

DB_FILE = "food_cache.db"

def init_cache_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS cache (
            food_item TEXT PRIMARY KEY,
            nutrition_data TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_from_cache(food_item: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT nutrition_data FROM cache WHERE food_item=?", (food_item,))
    result = c.fetchone()
    conn.close()
    if result:
        return json.loads(result[0])
    return None

def add_to_cache(food_item: str, nutrition_data: dict):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO cache (food_item, nutrition_data) VALUES (?, ?)",
              (food_item, json.dumps(nutrition_data)))
    conn.commit()
    conn.close()

# Initialize the database when the module is imported
init_cache_db()
