import database as db

if __name__ == "__main__":
    print("Создание таблиц в базе данных...")
    db.create_tables()
    print("Таблицы созданы успешно!")
