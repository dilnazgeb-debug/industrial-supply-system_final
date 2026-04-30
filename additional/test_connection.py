from database.db_manager import DatabaseManager

PG_DSN = "insert your own PostgreSQL DSN here"  # insert your own PostgreSQL DSN here
db = DatabaseManager(pg_dsn=PG_DSN).connect()

print("✅ Подключение успешно!")
print(f"Backend: {db._backend}")

if db._backend == "postgresql":
    cur = db._conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    tables = [row[0] for row in cur.fetchall()]
elif db._backend == "sqlite":
    cur = db._conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]

print("Таблицы в БД:", tables)
db.close()
