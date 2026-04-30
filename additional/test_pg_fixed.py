from database.db_manager import DatabaseManager
import sys

PG_DSN = "insert your own PostgreSQL DSN here"  # insert your own PostgreSQL DSN here
db = DatabaseManager(pg_dsn=PG_DSN).connect()

print("✅ Backend:", db._backend)
print("✅ Подключение успешно!")

if db._backend == "postgresql":
    cur = db._conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    tables = [row[0] for row in cur.fetchall()]
    print("PostgreSQL таблицы:", tables)
    
    # Тестовая вставка
    cur.execute("SELECT 1")
    print("✅ PostgreSQL запрос работает!")
    
elif db._backend == "sqlite":
    print("🔄 Fallback на SQLite")

db.close()
print("✅ Тест завершен")

