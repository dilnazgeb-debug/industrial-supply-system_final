# System Integration Guide - Complete Setup ✅

## Overview
Все части системы собраны вместе:
- 🏠 **Главная страница** с навигацией на все модули
- 🏭 **Управление поставщиками** (парсинг, просмотр, фильтрация)
- ⚙️ **Управление оборудованием** (аудит, классификация, PDFпарсинг)
- 📊 **Аналитика и прогнозирование** (спрос, цепь поставок)

---

## 🚀 Quick Start

### 1. Запуск приложения
```bash
cd /
python3 app_hybrid.py
```

Перейти на: **http://localhost:5052**

### 2. Вход
- **Логин:** dilnazshanova
- **Пароль:** Aa1234

---

## 📋 Модули и их маршруты

### 🏢 **Управление поставщиками**
```
Route: /suppliers
Features:
  ✓ Просмотр всех поставщиков
  ✓ Поиск по названию/стране
  ✓ Фильтрация по стране
  ✓ Парсинг поставщиков с интернета (кнопка "Scrape")
  ✓ Просмотр контактов и товаров
  ✓ Модальные окна с деталями
```

### 📦 **Каталог товаров**
```
Route: /products
Features:
  ✓ Список всех товаров от всех поставщиков
  ✓ Поиск по компании/модели/типу
  ✓ Фильтрация товаров в реальном времени
  ✓ Информация о ценах и характеристиках
```

### 🔗 **Цепь поставок**
```
Route: /supply-chain
Features:
  ✓ Статистика (количество поставщиков, товаров, выручка)
  ✓ Визуализация связей между поставщиками и товарами
  ✓ Информация о доступности товаров
```

### 📊 **Прогнозирование спроса**
```
Route: /forecast
Features:
  ✓ 4 метода прогнозирования:
    - Linear Regression
    - Exponential Smoothing
    - ARIMA
    - Machine Learning
  ✓ Выбор периода: 3/6/12 месяцев
  ✓ Интерактивные графики (Chart.js)
  ✓ Таблица с доверительными интервалами
  ✓ Нижние и верхние границы прогноза
```

### ⚙️ **Управление оборудованием**
```
Routes:
  /dashboard       - Панель управления оборудованием
  /audit           - Аудит и классификация оборудования
  /upload-pdf      - Загрузка и парсинг PDF документов
  /pdf-results     - Просмотр извлеченных данных
  
Features:
  ✓ Классификация BERT с точностью
  ✓ ML прогнозирование отказов
  ✓ Парсинг PDF с извлечением параметров
  ✓ Знание база (RAG)
  ✓ Интерактивная редакция результатов
  ✓ Сохранение в БД с логированием
```

---

## 🔄 Парсинг поставщиков

### Как работает
1. На странице `/suppliers` есть кнопка "🌥️ Scrape Suppliers"
2. При клике:
   - Система пытается спарсить реальные сайты
   - Если удалось → загружает свежие данные
   - Если нет → использует fallback данные (FALLBACK_DATA из web_scraper.py)
3. Результаты отображаются в таблице

### FALLBACK_DATA включает
- Shanghai Kaishan Compressor
- Fusheng Industrial
- DENAIR Energy Saving
- Sino Compressor Manufacturing
- SGS Industrial Equipment
- Jucai Pneumatic Equipment

Каждый с:
- Контактными данными (email, phone, WhatsApp, WeChat)
- Товарами (модель, тип, давление, мощность, цена)
- Информацией о стране/городе

---

## 📄 Структура URL

### API Endpoints
```
GET  /api/suppliers-data      → Supplier data
GET  /api/suppliers-scrape    → Web scraping
POST /api/audit               → Run equipment audit
POST /api/audit-recalculate   → Recalculate ML
POST /api/save-to-db          → Save to DB
```

### Page Routes
```
GET  /                    → Home (main page)
GET  /login               → Login page
GET  /dashboard           → Equipment dashboard
GET  /audit               → Audit form
GET  /upload-pdf          → PDF upload
GET  /pdf-results         → Extracted data
GET  /suppliers           → Suppliers page
GET  /products            → Products page
GET  /supply-chain        → Supply chain view
GET  /forecast            → Forecasting page
```

---

## 🧪 Тестирование

### Тест 1: Парсинг поставщиков
```
1. Перейти на /suppliers
2. Нажать кнопку "Scrape Suppliers"
3. Дождаться загрузки данных
4. Убедиться что таблица заполнена
5. Кликнуть на View для просмотра деталей
```

### Тест 2: Просмотр товаров
```
1. Перейти на /products
2. Ввести текст в поиск
3. Убедиться что таблица фильтруется в реальном времени
4. Проверить цены и характеристики
```

### Тест 3: Цепь поставок
```
1. Перейти на /supply-chain
2. Убедиться что статистика загружена (количество, выручка)
3. Посмотреть таблицу связей
```

### Тест 4: Прогнозирование
```
1. Перейти на /forecast
2. Выбрать метод прогнозирования
3. Выбрать период (3/6/12 месяцев)
4. Убедиться что график обновился
5. Проверить таблицу данных
```

### Тест 5: Аудит оборудования
```
1. Перейти на /audit
2. Ввести описание оборудования (на EN или RU)
3. Нажать "Run Audit"
4. Убедиться что система классифицировала тип
5. Проверить ML прогноз риска отказа
```

### Тест 6: Upload PDF
```
1. Перейти на /upload-pdf
2. Загрузить PDF (или перейти на /pdf-results если уже был)
3. Убедиться что данные извлечены
4. Отредактировать параметры
5. Нажать "Recalculate" и "Save to DB"
```

---

## 📊 Интеграционная схема

```
┌─────────────────────────────────────────────────────────┐
│                    Index (Home Page)                     │
│  [Suppliers] [Equipment] [PDF] [Analytics & Forecast]   │
└──────────┬──────────────┬──────────┬────────────────────┘
           │              │          │
           ▼              ▼          ▼
      ┌────────┐    ┌─────────┐  ┌──────────┐
      │Suppliers    │Equipment │  │Analytics │
      ├────────┤    ├─────────┤  ├──────────┤
      │/suppliers   │/dashboard│  │/forecast │
      │/products    │/audit    │  │/supply...│
      │/api/...     │/upload...│  │          │
      └────────┘    └─────────┘  └──────────┘
```

---

## 🔌 Технический стек

- **Backend:** Flask 3.0.0
- **Frontend:** Bootstrap 5 + Vanilla JS
- **DB:** PostgreSQL (local) / SQLite (production)
- **ML:** scikit-learn, XGBoost, sentence-transformers
- **PDF:** pdfplumber
- **Charts:** Chart.js
- **Scraping:** BeautifulSoup, requests

---

## ⚙️ Файлы которые были обновлены

```
✅ app_hybrid.py          - Добавлены 5 новых routes
✅ templates/index.html   - Новая главная страница с меню
✅ templates/suppliers.html - Полное управление поставщиками
✅ templates/products.html  - Каталог товаров
✅ templates/supply-chain.html - Визуализация цепи
✅ templates/forecast.html  - Прогнозирование спроса
```

---

## 🚨 Возможные проблемы и решения

| Проблема | Решение |
|----------|---------|
| 404 при переходе на /suppliers | Убедитесь что в app_hybrid.py добавлены route'ы |
| Нет данных в таблице | Проверьте /api/suppliers-data возвращает данные |
| PDF не загружается | Проверьте pdfplumber установлен: `pip install pdfplumber` |
| Нет BERT классификации | Нужна sentence-transformers: `pip install sentence-transformers` |
| БД не сохраняет | Установите DATABASE_URL переменную окружения |

---

## 📝 Следующие шаги

1. **Groq AI интеграция** (в процессе)
   - Добавить LLM-based parameter extraction
   - Использовать llama3-8b модель

2. **Улучшения UI**
   - Темная тема
   - Mobile responsive optimization
   - Real-time notifications

3. **Расширения функционала**
   - OCR для сканированных PDF
   - Автоматическое переобучение моделей
   - Интеграция с ERP системами

---

