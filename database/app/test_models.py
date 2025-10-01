import sys
import os
sys.path.append(os.path.dirname(__file__))

from models import Base, User, Task
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://postgres:Zz07022005@localhost/timewise_db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

def create_tables():
    Base.metadata.create_all(bind=engine)
    print("ТАБЛИЦЫ СОЗДАНЫ В POSTGRESQL!")

# Создаем таблицы
create_tables()

# 1. СОЗДАЕМ И СОХРАНЯЕМ ПОЛЬЗОВАТЕЛЯ ПЕРВЫМ
test_user = User(
    user_id=123456789,
    username="test_user", 
    first_name="Иван",
    last_name="Петров"
)

print("СОХРАНЯЕМ ПОЛЬЗОВАТЕЛЯ...")
db.add(test_user)
db.commit()  # ← ВАЖНО: сначала коммитим пользователя!
print("ПОЛЬЗОВАТЕЛЬ СОХРАНЕН!")

# 2. ТЕПЕРЬ СОЗДАЕМ ЗАДАЧУ ДЛЯ ЭТОГО ПОЛЬЗОВАТЕЛЯ
test_task = Task(
    user_id=123456789,  # тот же ID что у пользователя
    title="Тестовая задача",
    task_type="учеба", 
    duration_minutes=60,
    priority="high"
)

print("СОХРАНЯЕМ ЗАДАЧУ...")
db.add(test_task)
db.commit()  # ← Коммитим задачу
print("ЗАДАЧА СОХРАНЕНА!")

# ПРОВЕРЯЕМ
users_count = db.query(User).count()
tasks_count = db.query(Task).count()

print(f"Пользователей в базе: {users_count}")
print(f"Задач в базе: {tasks_count}")

if users_count > 0 and tasks_count > 0:
    print("УСПЕХ: Все данные сохранены в PostgreSQL!")
else:
    print("ОШИБКА: Данные не сохранились!")

db.close()