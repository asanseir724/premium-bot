"""
کانفیگ سیستم لاگینگ پیشرفته برای ربات تلگرام و API
"""

import os
import logging
import logging.handlers
from datetime import datetime

# مسیر پوشه لاگ‌ها
LOG_DIR = "logs"

# اطمینان از وجود پوشه لاگ
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# فرمت لاگ‌ها
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
DEBUG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d) - %(message)s"

# ایجاد فایل لاگ روزانه
def get_log_file(prefix):
    today = datetime.now().strftime('%Y-%m-%d')
    return os.path.join(LOG_DIR, f"{prefix}_{today}.log")

# پیکربندی لاگر اصلی
def setup_logger(name, level=logging.INFO, log_file=None, max_bytes=10*1024*1024, backup_count=5):
    """
    راه‌اندازی یک لاگر با فایل چرخشی
    :param name: نام لاگر
    :param level: سطح لاگینگ 
    :param log_file: مسیر فایل لاگ
    :param max_bytes: حداکثر اندازه هر فایل لاگ
    :param backup_count: تعداد فایل‌های پشتیبان
    :return: لاگر پیکربندی شده
    """
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # حذف هندلرهای موجود
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # فرمت لاگ بسته به سطح لاگینگ
    if level <= logging.DEBUG:
        formatter = logging.Formatter(DEBUG_FORMAT)
    else:
        formatter = logging.Formatter(LOG_FORMAT)
    
    # هندلر کنسول
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # هندلر فایل با چرخش خودکار
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, 
            maxBytes=max_bytes, 
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

# لاگرهای پیش‌فرض برای بخش‌های مختلف سیستم
def get_telegram_logger(level=logging.DEBUG):
    """لاگر مخصوص ربات تلگرام"""
    return setup_logger(
        'telegram_bot', 
        level=level, 
        log_file=get_log_file('telegram')
    )

def get_api_logger(level=logging.DEBUG):
    """لاگر مخصوص API"""
    return setup_logger(
        'api', 
        level=level, 
        log_file=get_log_file('api')
    )

def get_payment_logger(level=logging.DEBUG):
    """لاگر مخصوص پرداخت‌ها"""
    return setup_logger(
        'payment', 
        level=level, 
        log_file=get_log_file('payment')
    )

def get_database_logger(level=logging.DEBUG):
    """لاگر مخصوص دیتابیس"""
    return setup_logger(
        'database', 
        level=level, 
        log_file=get_log_file('database')
    )

def get_webhook_logger(level=logging.DEBUG):
    """لاگر مخصوص وب‌هوک‌ها"""
    return setup_logger(
        'webhook', 
        level=level, 
        log_file=get_log_file('webhook')
    )

def get_callback_logger(level=logging.DEBUG):
    """لاگر مخصوص callback‌های تلگرام"""
    return setup_logger(
        'callback', 
        level=level, 
        log_file=get_log_file('callback')
    )

# لاگر عمومی برای کل برنامه
def get_app_logger():
    """لاگر عمومی برنامه"""
    return setup_logger(
        'app', 
        level=logging.INFO, 
        log_file=os.path.join(LOG_DIR, 'app.log')
    )

# تنظیم لاگرهای کتابخانه‌های خارجی
def setup_external_loggers():
    """تنظیم لاگینگ برای کتابخانه‌های خارجی"""
    # تنظیم لاگر telebot
    telebot_logger = setup_logger(
        'telebot', 
        level=logging.INFO, 
        log_file=os.path.join(LOG_DIR, 'telebot.log')
    )
    
    # تنظیم لاگر sqlalchemy
    sqlalchemy_logger = setup_logger(
        'sqlalchemy.engine', 
        level=logging.WARNING, 
        log_file=os.path.join(LOG_DIR, 'sqlalchemy.log')
    )
    
    # تنظیم لاگر requests
    requests_logger = setup_logger(
        'requests', 
        level=logging.WARNING, 
        log_file=os.path.join(LOG_DIR, 'requests.log')
    )
    
    # تنظیم لاگر urllib3
    urllib3_logger = setup_logger(
        'urllib3', 
        level=logging.WARNING, 
        log_file=os.path.join(LOG_DIR, 'urllib3.log')
    )

# تنظیم تمام لاگرهای سیستم
def setup_all_loggers():
    """تنظیم تمام لاگرهای سیستم"""
    # لاگرهای داخلی
    telegram_logger = get_telegram_logger()
    api_logger = get_api_logger()
    payment_logger = get_payment_logger()
    database_logger = get_database_logger()
    webhook_logger = get_webhook_logger()
    callback_logger = get_callback_logger()
    app_logger = get_app_logger()
    
    # لاگرهای خارجی
    setup_external_loggers()
    
    # تنظیم لاگر ریشه
    root_logger = setup_logger(
        'root', 
        level=logging.WARNING, 
        log_file=os.path.join(LOG_DIR, 'root.log')
    )
    
    return {
        'telegram': telegram_logger,
        'api': api_logger,
        'payment': payment_logger,
        'database': database_logger,
        'webhook': webhook_logger,
        'callback': callback_logger,
        'app': app_logger,
        'root': root_logger
    }