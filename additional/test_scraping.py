#!/usr/bin/env python3
"""
TEST SCRIPT - проверка веб-скрепинга
Запустите: python3 test_scraping.py
"""

import sys
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("TEST")

# Импортируем функции из проекта
from scraper.web_scraper import scrape_supplier, _safe_request
import requests
from bs4 import BeautifulSoup

print("=" * 80)
print("🔍 ТЕСТ ВЕБ-СКРЕПИНГА")
print("=" * 80)
print()

# Тестовые URL
test_urls = [
    "https://www.kaishangroup.com/en",
    "https://www.denair.net",
    "https://www.alibaba.com/showroom/air-compressor-manufacturer.html",
    "https://www.made-in-china.com/products-search/hot-china-products/Air_Compressor.html",
]

print(f"Время теста: {datetime.now()}")
print(f"Всего URL для тестирования: {len(test_urls)}")
print()
print("-" * 80)
print()

for i, url in enumerate(test_urls, 1):
    print(f"✓ ТЕСТ #{i}: {url}")
    print("-" * 80)
    
    # Проверяем доступность
    try:
        print(f"  1️⃣  Попытка подключиться к {url}...")
        response = requests.head(url, timeout=5)
        print(f"     ✅ HTTP статус: {response.status_code}")
    except requests.exceptions.Timeout:
        print(f"     ❌ Таймаут (сайт слишком долго отвечает)")
    except requests.exceptions.ConnectionError:
        print(f"     ❌ Ошибка подключения (сайт недоступен или заблокирован)")
    except Exception as e:
        print(f"     ⚠️  Ошибка: {type(e).__name__}")
    
    # Пытаемся скрепить
    print(f"\n  2️⃣  Запуск web_scraper.scrape_supplier()...")
    try:
        data = scrape_supplier(url)
        
        source = data.get("_source", "unknown")
        print(f"     📊 Источник данных: {source}")
        
        if source == "live":
            print(f"     ✅ ДАННЫЕ ПОЛУЧЕНЫ!")
            print(f"        • Компания: {data.get('company_name', 'N/A')}")
            print(f"        • Email: {data.get('contacts', {}).get('email', 'N/A')}")
            print(f"        • Телефон: {data.get('contacts', {}).get('phone', 'N/A')}")
            if data.get('products'):
                print(f"        • Найдено продуктов: {len(data['products'])}")
        else:
            print(f"     🔄 Используются СИНТЕТИЧЕСКИЕ данные")
            print(f"        Причина: HTML парсинг не удался или не содержал достаточно информации")
            print(f"        • Компания: {data.get('company_name', 'N/A')}")
            
    except Exception as e:
        print(f"     ❌ ОШИБКА: {str(e)}")
    
    print()
    print()

print("=" * 80)
print("🏁 ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
print("=" * 80)
print()
print("РЕЗУЛЬТАТЫ:")
print("  • 'live' = Реальные данные с сайта (веб-скрепинг СРАБОТАЛ)")
print("  • 'simulated' = Синтетические данные (веб-скрепинг НЕ СРАБОТАЛ)")
print()
print("ВЫВОД:")
print("  Если большинство - 'simulated':")
print("    → Сайты блокируют автоматический доступ (anti-bot)")
print("    → Нужно использовать Selenium или API")
print()
print("  Если несколько 'live':")
print("    → КОД ДЕЙСТВИТЕЛЬНО ПАРСИТ РЕАЛЬНЫЕ ДАННЫЕ! ✅")
print()
