# Руководство по развёртыванию

## Содержание

1. [Быстрый старт](#быстрый-старт)
2. [Архитектура](#архитектура)
3. [Настройка окружения](#настройка-окружения)
4. [Локальная разработка](#локальная-разработка)
5. [Docker развёртывание](#docker-развёртывание)
6. [PostgreSQL настройка](#postgresql-настройка)
7. [Логирование и мониторинг](#логирование-и-мониторинг)
8. [Диагностика и отладка](#диагностика-и-отладка)

---

## Быстрый старт

### 1. Клонирование и подготовка (5 минут)

```bash
# Клонирование репозитория
git clone <repo-url>
cd supplier_system

# Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# или
venv\Scripts\activate     # Windows

# Установка зависимостей
pip install -r requirements-production.txt

# Копирование шаблона переменных окружения
cp .env.example .env
```

### 2. Запуск приложения

#### Режим JSON (демо без БД)

```bash
# Нет необходимости в DATABASE_URL - используется demo_data.json
export FLASK_DEBUG=0
export FLASK_ENV=production
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

python app_hybrid.py
```

**Результат:** приложение запускается на http://localhost:5052
- Логин: `dilnazshanova` / `Aa1234`
- Данные: оборудования из демо-набора
- БД не требуется
- 100% автономный режим

#### Режим PostgreSQL

```bash
# Установка PostgreSQL (macOS)
brew install postgresql

# Запуск PostgreSQL
brew services start postgresql

# Создание БД
createdb -U postgres supply_chain_data_lake

# Установка переменных окружения
export DATABASE_URL="postgresql://postgres:password@localhost:5432/supply_chain_data_lake"
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export GROQ_API_KEY="gsk_xxx..."  # Опционально

python app_hybrid.py
```

#### Docker Compose (полный стек)

```bash
# Запуск всей инфраструктуры
docker-compose -f infrastructure/docker-compose.yml up -d

# Установка переменных для Flask
export DATABASE_URL="postgresql://analytics:secure_password_123@localhost:5432/supply_chain_data_lake"

# Запуск приложения Flask
python -m flask run --host 0.0.0.0
```

---

## Архитектура

### Диаграмма архитектуры

```
┌─────────────────────────────────────────────────────────────┐
│                     СЛОЙ ПРЕДСТАВЛЕНИЯ (Браузер)             │
│  HTML/Jinja2 Шаблоны + JavaScript (fetch API)                │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/HTTPS
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                   ПРИЛОЖЕНИЕ FLASK                           │
│  app_hybrid.py (Порт 5000)                                   │
│  - Обработчики маршрутов (@app.route)                        │
│  - Управление сеансами (@login_required)                     │
│  - Абстракция БД (JSON vs PostgreSQL)                        │
└────────────────────────┬────────────────────────────────────┘
                         │
            ┌────────────┴──────────────┐
            ↓                           ↓
    ┌──────────────────┐        ┌──────────────────┐
    │  JSON режим      │        │ PostgreSQL режим │
    │  demo_data.json  │        │   Production БД  │
    │  (JSON Manager)  │        │  (SQLAlchemy)    │
    └──────────────────┘        └──────────────────┘
```

### Выбор режима: JSON vs PostgreSQL

```python
# В app_hybrid.py (строка 47):
DATABASE_URL = os.environ.get('DATABASE_URL')
IS_PRODUCTION_MODE = DATABASE_URL is None or DATABASE_URL == ""

if IS_PRODUCTION_MODE:
    # Использование JSON (демо режим)
    equipment = json_manager.get_all()
else:
    # Использование PostgreSQL (production)
    equipment = IndustrialEquipment.query.all()
```

**JSON режим:**
- Используется когда `DATABASE_URL` не установлена или пуста
- Данные загружаются из встроенного файла `demo_data.json`
- Фиксированное количество записей (234 примера)
- Подходит для облачных окружений и демонстраций

**PostgreSQL режим:**
- Используется когда `DATABASE_URL` установлена
- Подключается к БД через SQLAlchemy ORM
- Данные динамические, с поддержкой CRUD операций
- Подходит для разработки и локального тестирования

---

## Настройка окружения

### 1. Переменные окружения

Создайте файл `.env`:

```bash
# Копирование шаблона
cp .env.example .env

# Редактирование с вашими значениями
nano .env
```

**Минимально требуемые:**

```bash
# Для PostgreSQL:
DATABASE_URL=postgresql://user:pass@localhost:5432/db_name

# Или для JSON режима (оставить пусто):
DATABASE_URL=

# Обязательно
SECRET_KEY=your_secret_key_here
FLASK_ENV=production
FLASK_DEBUG=0

# Опционально (для LLM обработки):
GROQ_API_KEY=gsk_xxx...
```

**Загрузка в сеанс:**

```bash
# Linux/macOS
export $(cat .env | grep -v '#' | xargs)

# Windows PowerShell
Get-Content .env | ForEach-Object {
    if ($_ -notmatch '^\s*#' -and $_ -match '=') {
        $key, $value = $_ -split '=', 2
        [Environment]::SetEnvironmentVariable($key, $value)
    }
}
```

### 2. Генирирование SECRET_KEY

```python
python3 -c "import secrets; print(secrets.token_hex(32))"
# Результат: a7f8c2b9e1d4f3a6c5b8e9d0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8**
```

Установка:
```bash
export SECRET_KEY=a7f8c2b9e1d4f3a6c5b8e9d0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8**
```

---

## Локальная разработка

### 1. Окружение разработки

```bash
# Активация виртуального окружения
source venv/bin/activate

# Установка зависимостей для разработки
pip install -r requirements-production.txt
pip install pytest pytest-flask black flake8

# Создание .env.local для разработки
cat > .env.local << 'EOF'
FLASK_DEBUG=1
FLASK_ENV=development
DATABASE_URL=  # Использование JSON демо режима
SECRET_KEY=dev_key_not_secure_change_in_production
GROQ_API_KEY=optional_for_dev
EOF

# Загрузка переменных разработки
export $(cat .env.local | grep -v '#' | xargs)

# Запуск Flask dev сервера
flask run --reload
# Приложение доступно на http://localhost:5000
```

### 2. База данных (опционально)

```bash
# Запуск PostgreSQL
brew services start postgresql

# Создание БД разработки
createdb supply_chain_dev

# Выполнение миграций (если используются)
alembic upgrade head

# Начальный импорт данных (опционально)
python -c "from main import step4_simulate_supply_chain; step4_simulate_supply_chain(...)"
```

### 3. Тестирование

```bash
# Запуск всех тестов
pytest

# Запуск с покрытием
pytest --cov=.

# Запуск конкретного теста
pytest tests/test_audit.py::test_intelligent_audit

# Подробный вывод
pytest -vv
```

### 4. Проверка качества кода

```bash
# Форматирование с Black
black .

# Lint с Flake8
flake8 . --max-line-length=100 --exclude=venv

# Проверка типов с Pylint
pylint app_hybrid.py --disable=all --enable=W
```

---

## Docker развёртывание

### 1. Сборка образа

```bash
# Сборка Dockerfile
docker build -t supplier-system:latest .

# Сборка с тегом версии
docker build -t supplier-system:1.0.0 .

# Сборка с аргументами сборки
docker build \
    --build-arg PYTHON_VERSION=3.9 \
    -t supplier-system:latest .

# Проверка размера образа
docker images supplier-system
```

### 2. Запуск контейнера

```bash
# Базовый запуск (JSON режим)
docker run -p 5000:5000 supplier-system:latest

# С PostgreSQL
docker run \
    -p 5000:5000 \
    -e DATABASE_URL="postgresql://user:pass@postgres-host:5432/db" \
    -e SECRET_KEY="your_secret_key" \
    supplier-system:latest

# С монтированием томов
docker run \
    -p 5000:5000 \
    -v $(pwd)/models:/app/models \
    -v $(pwd)/outputs:/app/outputs \
    -e DATABASE_URL="..." \
    supplier-system:latest

# Фоновый режим
docker run -d --name supplier-app \
    -p 5000:5000 \
    -e DATABASE_URL="..." \
    supplier-system:latest

# Просмотр логов
docker logs -f supplier-app

# Остановка контейнера
docker stop supplier-app
```

### 3. Docker Compose

```bash
# Запуск полного стека
docker-compose -f infrastructure/docker-compose.yml up -d

# Проверка сервисов
docker-compose -f infrastructure/docker-compose.yml ps

# Просмотр логов
docker-compose -f infrastructure/docker-compose.yml logs -f app

# Масштабирование рабочих процессов
docker-compose -f infrastructure/docker-compose.yml up -d --scale spark-worker=3

# Остановка всех сервисов
docker-compose -f infrastructure/docker-compose.yml down
```

### 4. Сетевое взаимодействие Docker

```bash
# Просмотр сетей
docker network ls
docker network inspect supply_chain_network

# Подключение из Flask контейнера к PostgreSQL контейнеру:
# DATABASE_URL=postgresql://analytics:password@postgres:5432/supply_chain_data_lake
# (postgres = имя сервиса в docker-compose.yml)
```

---

## PostgreSQL настройка

### 1. Локальная установка

**macOS:**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**Linux (Ubuntu):**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

**Windows:**
- Скачать с https://www.postgresql.org/download/windows/
- Запустить инсталлятор, запомнить пароль

### 2. Создание БД

```sql
-- Подключение как суперпользователь
psql -U postgres

-- Создание БД
CREATE DATABASE supply_chain_data_lake;

-- Создание пользователя
CREATE USER analytics WITH PASSWORD 'secure_password_123';

-- Выдача прав
GRANT ALL PRIVILEGES ON DATABASE supply_chain_data_lake TO analytics;
ALTER DATABASE supply_chain_data_lake OWNER TO analytics;

-- Выход
\q
```

### 3. Инициализация схемы

```bash
# Вариант A: Использование Alembic (рекомендуется)
alembic init alembic
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head

# Вариант B: Использование SQLAlchemy напрямую
python << 'EOF'
from app_hybrid import app, db
with app.app_context():
    db.create_all()
    print("✅ Таблицы БД созданы")
EOF
```

### 4. Проверка подключения

```bash
# Тестирование подключения из CLI
psql -U analytics -d supply_chain_data_lake -h localhost

# Список таблиц
\dt

# Проверка структуры таблицы
\d industrial_equipment

# Подсчёт записей
SELECT COUNT(*) FROM industrial_equipment;

# Выход
\q
```

---

## Логирование и мониторинг

### 1. Логи приложения

```python
# Уже настроено в app_hybrid.py
import logging

logger = logging.getLogger(__name__)
logger.info("✅ Событие")
logger.warning("⚠️  Предупреждение")
logger.error("❌ Ошибка")
```

**Просмотр логов:**
```bash
# Flask dev сервер
flask run

# Gunicorn
gunicorn --access-logfile - --error-logfile - app_hybrid:app

# Docker
docker logs -f container_name

# Docker Compose
docker-compose logs -f app
```

### 2. Логирование запросов БД

```python
# Включение логирования SQLAlchemy
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

### 3. Отслеживание ошибок (Sentry)

```bash
# Установка
pip install sentry-sdk

# Настройка
import sentry_sdk
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    environment=os.environ.get("FLASK_ENV"),
    traces_sample_rate=0.1
)
```

### 4. Мониторинг производительности

```bash
# С py-spy
pip install py-spy
py-spy record -o profile.svg --pid <process_id>

# С memory-profiler
pip install memory-profiler
python -m memory_profiler app.py
```

---

## Диагностика и отладка

### Частые ошибки

**1. "ModuleNotFoundError: No module named 'app_hybrid'"**

```bash
# Убедитесь, что находитесь в корневой папке проекта
pwd  # Должно показать: .../supplier_system

# Установка зависимостей
pip install -r requirements-production.txt
```

**2. "DatabaseError: could not connect to server"**

```bash
# Проверка запуска PostgreSQL
brew services list  # macOS
systemctl status postgresql  # Linux

# Проверка формата DATABASE_URL
echo $DATABASE_URL
# Должно быть: postgresql://user:pass@host:port/database

# Тест подключения
psql $DATABASE_URL -c "SELECT 1"
```

**3. "404 - Page not found after login"**

```bash
# Проверка сеанса
# Добавьте отладку в маршрут:
@login_required
def dashboard():
    print(f"Session: {session}")
    ...
```

**4. "ML prediction returns None"**

```bash
# Проверка наличия моделей
ls -la models/
# Должны быть: pump.pkl, valve.pkl, и т.д.

# Проверка прав доступа
chmod 644 models/*.pkl
```

**5. "Groq API error"**

```bash
# Проверка API ключа
echo $GROQ_API_KEY

# Тестирование подключения
python -c "from groq import Groq; c = Groq(api_key='$GROQ_API_KEY'); print('✅')"

# Если ошибка: проверьте интернет, валидность ключа
```

### Режим отладки

```python
# В app_hybrid.py
app.config['DEBUG'] = True
app.config['TESTING'] = True

# Или через переменную окружения
export FLASK_DEBUG=1
flask run
```

### Просмотр состояния приложения

```python
# Flask shell
flask shell

# Проверка конфигурации
>>> app.config
>>> os.environ.get('DATABASE_URL')
>>> IS_PRODUCTION_MODE

# Проверка БД
>>> from app_hybrid import db, IndustrialEquipment
>>> IndustrialEquipment.query.count()
>>> db.session.query(IndustrialEquipment).first()

# Выход
>>> exit()
```
