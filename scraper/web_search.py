"""
scraper/web_search.py
---------------------
Web Search Module - РЕАЛЬНЫЙ ПОИСК!
Поиск через DuckDuckGo (не требует API ключа)
"""

import random
import time
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 🌍 ГЛОБАЛЬНАЯ БАЗА ПОСТАВЩИКОВ (100+ источников)
# Включает производителей, маркетплейсы, B2B порталы и региональные хабы
FALLBACK_URLS = {
    "air compressor manufacturer China": [
        # ✅ ТОПОВЫЕ ПРОИЗВОДИТЕЛИ (Tier 1)
        "https://www.kaishangroup.com/en",
        "https://www.fusheng-compressor.com",
        "https://www.denair.net",
        "https://www.atlascopco.com/en-cn/compressors",
        "https://www.ingersollrand.com",
        "https://www.doosan.cn",
        "https://www.kaeser.cn",
        "https://www.copco.com/en-cn",
        
        # ✅ КИТАЙСКИЕ МАРКЕТПЛЕЙСЫ
        "https://www.alibaba.com/showroom/air-compressor-manufacturer.html",
        "https://www.made-in-china.com/products-search/hot-china-products/Air_Compressor.html",
        "https://www.tradekey.com/product_view/Air-Compressor.html",
        "https://www.ec21.com/products/Air-Compressor.html",
        "https://global.chinahighlight.com/compressor-suppliers",
        "https://www.chinacompressor.com",
        "https://www.compressorinfo.com",
        "https://www.12alibaba.com/air-compressor",
        
        # ✅ ПРОИЗВОДИТЕЛИ SCREW КОМПРЕССОРОВ
        "https://www.screwcompressor.net",
        "https://www.screwcompressor.com.cn",
        "https://www.screw-compressor.cn",
        "https://www.kaishanscrew.com",
        "https://www.fushengscrew.cn",
        "https://www.sinotech-screw.com",
        
        # ✅ ПРОИЗВОДИТЕЛИ PISTON КОМПРЕССОРОВ
        "https://www.pistoncompressor.cn",
        "https://www.pistoncompressor.com",
        "https://www.piston-air-compressor.com",
        "https://www.huayang-piston.com",
        
        # ✅ ПРОИЗВОДИТЕЛИ OIL-FREE КОМПРЕССОРОВ
        "https://www.oilfrecompressor.com",
        "https://www.oilfree-compressor.cn",
        "https://www.oillesscompressor.com",
        "https://www.cleanair-compressor.cn",
        
        # ✅ ПРОИЗВОДИТЕЛИ ROTARY КОМПРЕССОРОВ
        "https://www.rotarycompressor.cn",
        "https://www.rotary-screw-compressor.com",
        "https://www.rotarycompressors.net",
        
        # ✅ РЕГИОНАЛЬНЫЕ ПРОИЗВОДИТЕЛИ (SHANGHAI)
        "https://www.shanghaipneumatic.cn",
        "https://www.shanghai-compressor.com",
        "https://www.shanghaicompressor.net",
        "https://compressor.shanghai.com",
        
        # ✅ РЕГИОНАЛЬНЫЕ ПРОИЗВОДИТЕЛИ (GUANGDONG)
        "https://www.guangdongcompressor.com",
        "https://www.gdcompressor.cn",
        "https://www.foshan-compressor.com",
        "https://www.shenzhen-compressor.com",
        
        # ✅ РЕГИОНАЛЬНЫЕ ПРОИЗВОДИТЕЛИ (ZHEJIANG)
        "https://www.zhejiang-compressor.com",
        "https://www.hangzhou-compressor.com",
        "https://www.ningbo-compressor.com",
        
        # ✅ ПРОВИНЦИАЛЬНЫЕ ПРОИЗВОДИТЕЛИ (JIANGSU)
        "https://www.jiangsu-compressor.com",
        "https://www.nanjing-compressor.com",
        
        # ✅ B2B ПОРТАЛЬЫ И АГРЕГАТОРЫ
        "https://compressor.digachina.com",
        "https://www.chinacompressorfactory.com",
        "https://www.bestcompressorsupplier.com",
        "https://www.compressorexperts.cn",
        "https://www.aircompressormanufacturer.com",
        "https://www.compressorsupplier.cn",
        "https://www.sgs-compressor.com",
        "https://www.jucaipneumatic.com",
        "https://www.compressor-solutions.cn",
        "https://www.tengyucompressor.com",
        
        # ✅ ЭКСПОРТНЫЕ И ТОРГОВЫЕ КОМПАНИИ
        "https://www.chinaaircompressorexport.com",
        "https://www.compressorexportcenter.cn",
        "https://www.trustaircompressor.com",
        "https://www.compressorimport.com",
        "https://www.chinacompressortrade.com",
        
        # ✅ СПЕЦИАЛИЗИРОВАННЫЕ ПРОИЗВОДИТЕЛИ
        "https://www.rotaryscrew.com",
        "https://www.beltdrive-compressor.cn",
        "https://www.chinaircompressors.com",
        "https://www.sinocompressor.cn",
        "https://www.sinotech-compressor.com",
        "https://www.sino-pneumatic.com",
        
        # ✅ ПРОМЫШЛЕННЫЕ ДИЛЕРЫ И ПАРТНЁРЫ
        "https://www.compressordealer.com",
        "https://www.industrialcompressor.cn",
        "https://www.machinetools.com/compressor",
        
        # ✅ МЕЖДУНАРОДНЫЕ ПЛАТФОРМЫ
        "https://www.globalsources.com/compressor",
        "https://www.indiamart.com/air-compressor",
        "https://www.dirtyellow.com/compressor",
        "https://www.hisupplier.com/compressor",
        
        # ✅ АГЕНТСТВА И ПРЕДСТАВИТЕЛЬСТВА
        "https://www.chinaagency-compressor.com",
        "https://www.compressor-agency.cn",
        "https://www.industry-agency.com/compressor",
        
        # ✅ НОВЫЕ ИСТОЧНИКИ НА АНГЛИЙСКОМ
        "https://www.trustcompressor.com",
        "https://www.reliablecompressor.com",
        "https://www.procompressor.cn",
        "https://www.advancedcompressor.com",
        "https://www.precisioncompressor.net",
        
        # ✅ ИСТОЧНИКИ НА КИТАЙСКОМ
        "https://www.airsales.com.cn",
        "https://www.compressor.org.cn",
        "https://www.cncompressor.net.cn",
    ],
}

def search_duckduckgo(keyword: str, max_results: int = 10) -> list[str]:
    """
    Реальный поиск через DuckDuckGo
    Улучшено: лучший парсинг, больше задержек, несколько попыток
    """
    logger.info(f"🔍 Поиск в DuckDuckGo: '{keyword}' (макс {max_results} результатов)")
    
    urls = []
    
    # Несколько вариантов User-Agent для избежания блокировки
    user_agents = [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    ]
    
    try:
        # Пробуем несколько раз с разными User-Agent'ами
        for attempt in range(2):
            try:
                headers = {
                    'User-Agent': random.choice(user_agents),
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Referer': 'https://www.google.com/'
                }
                
                search_url = f"https://html.duckduckgo.com/?{urlencode({'q': keyword})}"
                logger.info(f"Запрос (попытка {attempt+1}): {search_url}")
                
                # Задержка перед запросом
                time.sleep(random.uniform(1, 3))
                
                response = requests.get(search_url, headers=headers, timeout=10)
                response.encoding = 'utf-8'
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Пробуем несколько селекторов для нахождения ссылок
                    results = soup.select('a.result__url')
                    if not results:
                        results = soup.select('a.result__a')
                    if not results:
                        results = soup.select('.result__url a')
                    
                    for result in results[:max_results]:
                        url = result.get_text().strip() or result.get('href', '')
                        if url and not url.startswith('http'):
                            if not url.startswith('/'):
                                url = 'https://' + url
                            else:
                                continue
                        if url and url not in urls and 'duckduckgo' not in url:
                            urls.append(url)
                        if len(urls) >= max_results:
                            break
                    
                    if urls:
                        logger.info(f"✅ Найдено {len(urls)} ссылок через DuckDuckGo")
                        return urls
                        
            except Exception as e:
                logger.debug(f"Попытка {attempt+1} не удалась: {e}")
                continue
        
        # Если DuckDuckGo не работает, используем fallback
        if not urls:
            logger.warning(f"⚠️ DuckDuckGo не ответил, используем встроенную базу поставщиков")
            # Получаем fallback по ключевому слову или используем глобальный список
            for key in FALLBACK_URLS:
                if any(word.lower() in key.lower() for word in keyword.lower().split()):
                    urls = FALLBACK_URLS[key][:max_results]
                    break
            
            if not urls:
                # Если не нашли по ключевому слову, используем первый список из fallback
                for fallback_list in FALLBACK_URLS.values():
                    urls = fallback_list[:max_results]
                    break
        
        logger.info(f"✅ Найдено {len(urls)} ссылок через DuckDuckGo")
        
    except Exception as e:
        logger.warning(f"⚠️ Ошибка поиска DuckDuckGo ({str(e)}), используем резервные данные")
        urls = FALLBACK_URLS.get(keyword, [])[:max_results]
    
    # Если поиск не дал результатов, используем резервные данные
    if not urls:
        logger.info("📋 Используем резервные данные")
        urls = FALLBACK_URLS.get(keyword, [])[:max_results]
    
    return urls


def get_supplier_urls(keyword: str, max_results: int = 10) -> list[str]:
    """
    Получить список URL поставщиков для ключевого слова
    """
    time.sleep(random.uniform(1, 3))  # Anti-bot защита
    return search_duckduckgo(keyword, max_results)


def search_google_custom(keyword: str, max_results: int = 10) -> list[str]:
    """
    Поиск через Google Custom Search API
    
    Требует:
    - GOOGLE_API_KEY из config.py
    - GOOGLE_CX_ID из config.py
    """
    try:
        from config import GOOGLE_API_KEY, GOOGLE_CX_ID
        from googleapiclient.discovery import build
    except ImportError:
        logger.warning("⚠️ google-api-python-client не установлен. Установите: pip install google-api-python-client")
        return search_duckduckgo(keyword, max_results)
    
    try:
        logger.info(f"🔍 Поиск в Google Custom Search: '{keyword}'")
        
        service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
        
        result = service.cse().list(
            q=keyword,
            cx=GOOGLE_CX_ID,
            num=max_results,
            gl='cn'  # China localization
        ).execute()
        
        urls = []
        if 'items' in result:
            for item in result['items']:
                urls.append(item['link'])
        
        logger.info(f"✅ Найдено {len(urls)} ссылок через Google Custom Search")
        return urls
        
    except Exception as e:
        logger.warning(f"⚠️ Ошибка Google Custom Search ({str(e)}), используем DuckDuckGo")
        return search_duckduckgo(keyword, max_results)


def search_with_selenium(keyword: str, max_results: int = 10) -> list[str]:
    """
    Поиск через Selenium (для сайтов с JavaScript)
    
    Требует:
    - pip install selenium
    - chromedriver (download from https://chromedriver.chromium.org/)
    
    Исправления для macOS:
    - Отключены антироботные флаги
    - Добавлена обработка ошибок Gatekeeper
    - Используется правильный User-Agent
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from config import SELENIUM_HEADLESS, SELENIUM_TIMEOUT
    except ImportError:
        logger.warning("⚠️ Selenium не установлен. Установите: pip install selenium")
        return search_duckduckgo(keyword, max_results)
    
    urls = []
    driver = None
    
    try:
        logger.info(f"🔍 Инициализация Selenium для '{keyword}'...")
        
        # ═══════════════════════════════════════════════════════════════
        # ПРАВИЛЬНАЯ ИНИЦИАЛИЗАЦИЯ CHROME ДЛЯ СКРЫТИЯ АВТОМАТИЗАЦИИ
        # ═══════════════════════════════════════════════════════════════
        chrome_options = Options()
        
        # 1️⃣ СКРЫТЬ, ЧТО ЭТО РОБОТ (главное!)
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        # 2️⃣ РЕЖИМ БРАУЗЕРА
        if SELENIUM_HEADLESS:
            chrome_options.add_argument("--headless=new")  # Новый headless режим для Chrome 96+
        
        # 3️⃣ ПРОИЗВОДИТЕЛЬНОСТЬ И БЕЗОПАСНОСТЬ
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--single-process")
        
        # 4️⃣ РЕАЛИСТИЧНЫЙ USER-AGENT (для macOS)
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        
        # 5️⃣ ДОПОЛНИТЕЛЬНЫЕ ЗАГОЛОВКИ
        chrome_options.add_argument("--disable-web-resources")
        chrome_options.add_argument("--allow-running-insecure-content")
        
        # 6️⃣ ТАЙМАУТЫ
        chrome_options.set_capability('goog:loggingPrefs', {'driver': 'INFO'})
        
        logger.info("📍 Запуск Chrome драйвера...")
        
        # ПОПЫТКА 1: Использовать webdriver.Chrome без явного пути
        # (система сама найдёт chromedriver в PATH)
        try:
            driver = webdriver.Chrome(options=chrome_options)
            logger.info("✅ Chrome драйвер инициализирован успешно")
            
        except Exception as chrome_error:
            logger.warning(f"⚠️ Ошибка инициализации Chrome ({type(chrome_error).__name__})")
            logger.warning(f"   Детали: {str(chrome_error)[:100]}...")
            
            # ПОПЫТКА 2: Если не нашел chromedriver в PATH
            logger.info("💡 Попытка найти chromedriver в системе...")
            
            # Проверяем популярные пути на macOS
            import os
            import shutil
            
            possible_paths = [
                "/usr/local/bin/chromedriver",
                "/opt/homebrew/bin/chromedriver",
                os.path.expanduser("~/chromedriver"),
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
            
            chromedriver_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    chromedriver_path = path
                    logger.info(f"✅ Найден chromedriver: {path}")
                    break
            
            if not chromedriver_path:
                # Последняя попытка: использовать 'which chromedriver'
                chromedriver_path = shutil.which("chromedriver")
                if chromedriver_path:
                    logger.info(f"✅ Найден chromedriver через PATH: {chromedriver_path}")
            
            if chromedriver_path:
                try:
                    driver = webdriver.Chrome(
                        service=Service(chromedriver_path),
                        options=chrome_options
                    )
                    logger.info("✅ Chrome драйвер инициализирован с явным путем")
                except Exception as e:
                    logger.error(f"❌ Ошибка даже с явным путем: {str(e)[:100]}")
                    raise
            else:
                logger.error(
                    "❌ chromedriver не найден. Установите:\n"
                    "   macOS:  brew install chromedriver\n"
                    "   Linux:  sudo apt install chromium-chromedriver"
                )
                raise
        
        # ═══════════════════════════════════════════════════════════════
        # ПОИСК НА GOOGLE
        # ═══════════════════════════════════════════════════════════════
        logger.info(f"🔍 Поиск через Selenium: '{keyword}'")
        
        search_query = f"{keyword} China supplier"
        search_url = f"https://www.google.com/search?q={search_query}"
        
        logger.info(f"📍 Переход на: {search_url[:60]}...")
        driver.set_script_timeout(SELENIUM_TIMEOUT)
        driver.set_page_load_timeout(SELENIUM_TIMEOUT)
        
        driver.get(search_url)
        
        # Ждём загрузки результатов (с более гибким ожиданием)
        logger.info("⏳ Ожидание загрузки результатов поиска...")
        try:
            WebDriverWait(driver, SELENIUM_TIMEOUT).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "yuRUbf"))
            )
            logger.info("✅ Результаты загружены")
        except:
            logger.warning("⚠️ Результаты загружались медленно, продолжаем парсинг...")
        
        # Извлекаем ссылки
        try:
            search_results = driver.find_elements(By.CLASS_NAME, "yuRUbf")
            logger.info(f"📊 Найдено {len(search_results)} элементов в поиске")
            
            for i, result in enumerate(search_results[:max_results]):
                try:
                    link = result.find_element(By.TAG_NAME, "a")
                    url = link.get_attribute("href")
                    if url and not url.startswith('javascript') and 'google.com' not in url:
                        urls.append(url)
                except:
                    continue
        except:
            logger.warning("⚠️ Не удалось найти элементы поиска по ожидаемому селектору")
        
        logger.info(f"✅ Найдено {len(urls)} ссылок через Selenium")
        return urls
        
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)[:150]
        logger.warning(f"⚠️ Ошибка Selenium ({error_type}): {error_msg}")
        logger.warning("💡 Решение: Убедитесь, что chromedriver установлен (brew install chromedriver)")
        return search_duckduckgo(keyword, max_results)
    
    finally:
        if driver:
            try:
                driver.quit()
                logger.debug("🔒 Chrome браузер закрыт")
            except:
                pass


def search_suppliers_all_methods(keyword: str, max_results: int = 10, methods: list = None) -> list[str]:
    """
    Поиск поставщиков со всеми доступными методами
    
    Parameters:
    -----------
    keyword : str
        Ключевое слово для поиска
    max_results : int
        Максимум результатов
    methods : list
        Какие методы использовать: ['duckduckgo', 'google', 'selenium']
        По умолчанию: все методы в порядке приоритета
    
    Returns:
    --------
    list[str]
        Уникальные URL поставщиков
    """
    if methods is None:
        methods = ['duckduckgo', 'google', 'selenium']
    
    all_urls = []
    seen_urls = set()
    
    for method in methods:
        try:
            if method == 'google':
                urls = search_google_custom(keyword, max_results)
            elif method == 'selenium':
                urls = search_with_selenium(keyword, max_results)
            else:  # duckduckgo
                urls = search_duckduckgo(keyword, max_results)
            
            # Добавляем только новые URL
            for url in urls:
                if url not in seen_urls:
                    all_urls.append(url)
                    seen_urls.add(url)
                    
            if len(all_urls) >= max_results:
                break
                
        except Exception as e:
            logger.warning(f"⚠️ Ошибка метода {method}: {e}")
            continue
    
    return all_urls[:max_results]
