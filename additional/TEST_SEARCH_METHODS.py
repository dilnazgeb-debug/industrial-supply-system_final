#!/usr/bin/env python3
"""
TEST_SEARCH_METHODS.py
======================

Тестируем все 3 встроенных метода поиска поставщиков:
1. DuckDuckGo (по умолчанию)
2. Google Custom Search API
3. Selenium (браузер)
"""

import sys
import logging
from scraper.web_search import (
    search_duckduckgo,
    search_google_custom,
    search_with_selenium,
    search_suppliers_all_methods
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def test_duckduckgo():
    """Тест DuckDuckGo поиска"""
    print("\n" + "="*70)
    print("🔍 ТЕСТ 1: DuckDuckGo Поиск")
    print("="*70)
    
    keyword = "air compressor manufacturer China"
    print(f"\nКлючевое слово: {keyword}")
    print(f"Результатов запрошено: 5\n")
    
    urls = search_duckduckgo(keyword, max_results=5)
    
    print(f"\n✅ Найдено {len(urls)} результатов:")
    for i, url in enumerate(urls, 1):
        print(f"  {i}. {url}")
    
    return len(urls) > 0


def test_google():
    """Тест Google Custom Search"""
    print("\n" + "="*70)
    print("🔍 ТЕСТ 2: Google Custom Search API")
    print("="*70)
    
    keyword = "screw compressor supplier"
    print(f"\nКлючевое слово: {keyword}")
    print(f"Результатов запрошено: 5\n")
    
    try:
        urls = search_google_custom(keyword, max_results=5)
        
        print(f"\n✅ Найдено {len(urls)} результатов:")
        for i, url in enumerate(urls, 1):
            print(f"  {i}. {url}")
        
        return len(urls) > 0
        
    except Exception as e:
        print(f"\n⚠️ Ошибка: {e}")
        print("💡 Установите: pip install google-api-python-client")
        return False


def test_selenium():
    """Тест Selenium поиска"""
    print("\n" + "="*70)
    print("🔍 ТЕСТ 3: Selenium (Браузер)")
    print("="*70)
    
    keyword = "piston compressor manufacturer"
    print(f"\nКлючевое слово: {keyword}")
    print(f"Результатов запрошено: 5\n")
    
    try:
        urls = search_with_selenium(keyword, max_results=5)
        
        print(f"\n✅ Найдено {len(urls)} результатов:")
        for i, url in enumerate(urls, 1):
            print(f"  {i}. {url}")
        
        return len(urls) > 0
        
    except Exception as e:
        print(f"\n⚠️ Ошибка: {e}")
        print("💡 Установите: pip install selenium")
        print("💡 Загрузите chromedriver: https://chromedriver.chromium.org/")
        return False


def test_all_methods():
    """Тест всех методов вместе"""
    print("\n" + "="*70)
    print("🔍 ТЕСТ 4: ВСЕ МЕТОДЫ ВМЕСТЕ (с автоматическим fallback)")
    print("="*70)
    
    keyword = "industrial compressor China"
    print(f"\nКлючевое слово: {keyword}")
    print(f"Результатов запрошено: 10\n")
    print("Порядок методов: DuckDuckGo → Google → Selenium\n")
    
    urls = search_suppliers_all_methods(
        keyword=keyword,
        max_results=10,
        methods=['duckduckgo', 'google', 'selenium']
    )
    
    print(f"\n✅ Найдено {len(urls)} результатов из разных источников:")
    for i, url in enumerate(urls, 1):
        print(f"  {i}. {url}")
    
    return len(urls) > 0


def main():
    """Запуск всех тестов"""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " ТЕСТИРОВАНИЕ МЕТОДОВ ПОИСКА ПОСТАВЩИКОВ ".center(68) + "║")
    print("╚" + "="*68 + "╝")
    
    results = {
        "DuckDuckGo": test_duckduckgo(),
        "Google Custom Search": test_google(),
        "Selenium": test_selenium(),
        "Все методы": test_all_methods(),
    }
    
    print("\n" + "="*70)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("="*70)
    
    for method, passed in results.items():
        status = "✅ OK" if passed else "⚠️  ТРЕБУЕТ НАСТРОЙКИ"
        print(f"{method:30} {status}")
    
    print("\n" + "="*70)
    print("📝 РЕКОМЕНДАЦИИ")
    print("="*70)
    print("""
1. DuckDuckGo - всегда работает (встроен по умолчанию)
2. Google Custom Search - требует: pip install google-api-python-client
3. Selenium - требует: pip install selenium + chromedriver

Установка зависимостей:
    pip install -r requirements.txt

Использование в коде:
    from scraper.web_search import search_suppliers_all_methods
    
    urls = search_suppliers_all_methods(
        keyword="air compressor",
        max_results=20,
        methods=['duckduckgo', 'google', 'selenium']
    )
    """)
    
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
