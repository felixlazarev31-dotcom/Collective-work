import sqlite3


def migrate_database():
    conn = sqlite3.connect('instance/db.sqlite3')
    cursor = conn.cursor()

    # Проверяем какие колонки уже есть
    cursor.execute("PRAGMA table_info(todo)")
    columns = [col[1] for col in cursor.fetchall()]

    # Добавляем created_at если нет
    if 'created_at' not in columns:
        cursor.execute("ALTER TABLE todo ADD COLUMN created_at DATETIME")
        cursor.execute("UPDATE todo SET created_at = datetime('now') WHERE created_at IS NULL")
        print("✅ Добавлена колонка created_at")

    # Добавляем completed_at если нет
    if 'completed_at' not in columns:
        cursor.execute("ALTER TABLE todo ADD COLUMN completed_at DATETIME")
        # Для уже выполненных задач ставим дату выполнения
        cursor.execute("UPDATE todo SET completed_at = created_at WHERE complete = 1 AND completed_at IS NULL")
        print("✅ Добавлена колонка completed_at")

    conn.commit()
    conn.close()
    print("🎉 База данных успешно обновлена без потери данных!")


if __name__ == "__main__":
    migrate_database()