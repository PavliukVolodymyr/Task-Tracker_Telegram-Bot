import sqlite3

# Підключення до бази даних
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Створення таблиці для збереження токенів
cursor.execute('''
    CREATE TABLE IF NOT EXISTS tokens (
        chat_id INTEGER PRIMARY KEY,
        access_token TEXT,
        refresh_token TEXT
    )
''')

# Збереження змін у базі даних
conn.commit()

# Закриття підключення до бази даних
conn.close()
