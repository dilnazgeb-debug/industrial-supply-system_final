# PostgreSQL DSN for production pipeline
PG_DSN = "insert your own PostgreSQL DSN here" 

# ═══════════════════════════════════════════════════════════════
# GOOGLE CUSTOM SEARCH API CREDENTIALS
# ═══════════════════════════════════════════════════════════════
GOOGLE_API_KEY = "AIzaSyBc9VON74NNnBvpoT7nlxT2Q6CoG87vv**" # insert your own API key here
GOOGLE_CX_ID = "25a0de3e9c17d45**" # insert your own cx_id here

# ═══════════════════════════════════════════════════════════════
# SELENIUM CONFIGURATION (for JavaScript-heavy sites)
# ═══════════════════════════════════════════════════════════════
SELENIUM_ENABLED = False  # Set to True if chromedriver installed
SELENIUM_HEADLESS = True  # Run browser in headless mode (faster)
SELENIUM_TIMEOUT = 15     # Seconds to wait for page load

# ═══════════════════════════════════════════════════════════════
# SELENIUM ADVANCED OPTIONS (для избежания блокировок)
# ═══════════════════════════════════════════════════════════════
SELENIUM_DISABLE_AUTOMATION = True  # Скрыть, что это автоматизация
SELENIUM_USE_UNDETECTED_CHROME = False  # Использовать undetected-chromedriver если доступен
SELENIUM_RETRY_ON_ERROR = True  # Переподключаться при ошибке

# ═══════════════════════════════════════════════════════════════
# SELENIUM PATHS (для macOS, Linux, Windows)
# ═══════════════════════════════════════════════════════════════
# Оставьте пусто - система сама найдёт chromedriver
SELENIUM_CHROMEDRIVER_PATH = None

# Или укажите явно:
# SELENIUM_CHROMEDRIVER_PATH = "/usr/local/bin/chromedriver"
# SELENIUM_CHROMEDRIVER_PATH = "/opt/homebrew/bin/chromedriver"  # M1/M2 Mac

