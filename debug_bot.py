#!/usr/bin/env python3
"""
اسکریپت اجرای ربات تلگرام با لاگینگ پیشرفته برای عیب‌یابی
این اسکریپت با سطح لاگینگ DEBUG اجرا می‌شود و تمام جزئیات فعالیت ربات را ثبت می‌کند
"""

import os
import sys
import logging
import logging_config

# تنظیم لاگرهای سیستم
loggers = logging_config.setup_all_loggers()
logger = loggers['app']

# لاگ کردن شروع اسکریپت
logger.info("===== شروع اجرای ربات تلگرام در حالت دیباگ =====")

try:
    # وارد کردن ماژول‌های مورد نیاز
    from dotenv import load_dotenv
    import telebot
    from telebot import types
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    # بارگذاری متغیرهای محیطی
    load_dotenv()
    
    # لاگ کردن اطلاعات محیط
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Telebot version: {telebot.__version__}")
    
    # لاگ کردن مسیرهای سیستم
    logger.info(f"Current directory: {os.getcwd()}")
    logger.info(f"Log directory: {os.path.abspath('logs')}")
    
    # وارد کردن ماژول‌های پروژه
    import run_telegram_bot
    import models
    import config_manager
    
    # لاگ کردن اطلاعات پیکربندی
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if token:
        # فقط بخشی از توکن را به دلایل امنیتی نمایش می‌دهیم
        masked_token = token[:4] + "..." + token[-4:] if len(token) > 8 else "***"
        logger.info(f"Bot token loaded: {masked_token}")
    else:
        logger.error("Bot token not found in environment variables!")
    
    # بررسی اتصال به دیتابیس
    try:
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            # حذف بخش رمز عبور از URL دیتابیس برای لاگ کردن
            safe_db_url = database_url
            if '@' in database_url:
                prefix, suffix = database_url.split('@', 1)
                if ':' in prefix and '/' in prefix:
                    parts = prefix.split(':')
                    safe_parts = parts[:-1] + ['****']
                    safe_prefix = ':'.join(safe_parts)
                    safe_db_url = f"{safe_prefix}@{suffix}"
            
            logger.info(f"Database URL: {safe_db_url}")
            
            # تست اتصال به دیتابیس
            engine = create_engine(database_url)
            Session = sessionmaker(bind=engine)
            session = Session()
            
            # تست یک کوئری ساده
            result = session.execute("SELECT 1").fetchone()
            logger.info(f"Database connection test: {result}")
            
            # بررسی جداول
            from app import db
            table_names = db.inspect(engine).get_table_names()
            logger.info(f"Database tables: {table_names}")
            
        else:
            logger.error("Database URL not found in environment variables!")
    
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}", exc_info=True)
    
    # لاگ کردن پلن‌های اشتراک
    try:
        plans = config_manager.get_subscription_plans()
        logger.info(f"Subscription plans: {plans}")
    except Exception as e:
        logger.error(f"Error getting subscription plans: {str(e)}", exc_info=True)
    
    # ضبط تمام دستورات ربات
    def log_bot_command(command, message, response=None):
        """ثبت دستورات ربات و پاسخ‌های آن"""
        command_logger = loggers['telegram']
        user_id = message.from_user.id if hasattr(message, 'from_user') and message.from_user else "Unknown"
        username = message.from_user.username if hasattr(message, 'from_user') and message.from_user else "Unknown"
        
        log_message = (
            f"Command: {command}\n"
            f"From User: {user_id} (@{username})\n"
            f"Message: {message.text if hasattr(message, 'text') else message}\n"
        )
        
        if response:
            log_message += f"Response: {response}\n"
            
        command_logger.info(log_message)

    # ضبط تمام کالبک‌های ربات
    def log_callback_query(call):
        """ثبت کالبک‌های دریافتی ربات"""
        callback_logger = loggers['callback']
        user_id = call.from_user.id if hasattr(call, 'from_user') and call.from_user else "Unknown"
        username = call.from_user.username if hasattr(call, 'from_user') and call.from_user else "Unknown"
        
        log_message = (
            f"Callback Query: {call.data}\n"
            f"From User: {user_id} (@{username})\n"
            f"Message ID: {call.message.message_id if hasattr(call, 'message') else 'Unknown'}\n"
        )
            
        callback_logger.info(log_message)

    # هوک کردن متد‌های telebot برای ثبت لاگ
    original_send_message = run_telegram_bot.bot.send_message
    original_edit_message_text = run_telegram_bot.bot.edit_message_text
    original_register_next_step_handler = run_telegram_bot.bot.register_next_step_handler
    
    # جایگزینی متد send_message با نسخه لاگ کننده
    def logged_send_message(chat_id, text, *args, **kwargs):
        loggers['telegram'].debug(f"Sending message to {chat_id}: {text[:100]}...")
        return original_send_message(chat_id, text, *args, **kwargs)
    
    # جایگزینی متد edit_message_text با نسخه لاگ کننده
    def logged_edit_message_text(text, chat_id, message_id, *args, **kwargs):
        loggers['telegram'].debug(f"Editing message {message_id} in chat {chat_id}: {text[:100]}...")
        return original_edit_message_text(text, chat_id, message_id, *args, **kwargs)
    
    # جایگزینی متد register_next_step_handler با نسخه لاگ کننده
    def logged_register_next_step_handler(message, callback, *args, **kwargs):
        loggers['telegram'].debug(f"Registering next step handler for message {message.message_id}, callback: {callback.__name__}, args: {args}, kwargs: {kwargs}")
        return original_register_next_step_handler(message, callback, *args, **kwargs)
    
    # اعمال متدهای جدید
    run_telegram_bot.bot.send_message = logged_send_message
    run_telegram_bot.bot.edit_message_text = logged_edit_message_text
    run_telegram_bot.bot.register_next_step_handler = logged_register_next_step_handler
    
    # هوک کردن handle_callback_query برای لاگینگ
    original_handle_callback_query = run_telegram_bot.handle_callback_query
    
    def logged_handle_callback_query(call):
        log_callback_query(call)
        return original_handle_callback_query(call)
    
    run_telegram_bot.handle_callback_query = logged_handle_callback_query
    
    # هوک کردن process_username_step برای لاگینگ دقیق
    original_process_username_step = run_telegram_bot.process_username_step
    
    def logged_process_username_step(message, plan_id):
        loggers['telegram'].debug(f"Entered process_username_step with plan_id: {plan_id}")
        loggers['telegram'].debug(f"Message: {message.text if hasattr(message, 'text') else 'No text'}")
        loggers['telegram'].debug(f"From user: {message.from_user.id if hasattr(message, 'from_user') else 'Unknown'}")
        
        try:
            result = original_process_username_step(message, plan_id)
            loggers['telegram'].debug("process_username_step completed successfully")
            return result
        except Exception as e:
            loggers['telegram'].error(f"Error in process_username_step: {str(e)}", exc_info=True)
            # اطلاع رسانی به کاربر در صورت خطا
            run_telegram_bot.bot.send_message(
                message.chat.id,
                "⚠️ An error occurred while processing your order. Please try again or contact support."
            )
    
    run_telegram_bot.process_username_step = logged_process_username_step
    
    # اجرای ربات در حالت پولینگ با لاگینگ کامل
    logger.info("Starting bot in polling mode with debug logging...")
    
    # راه‌اندازی پولینگ با لاگینگ خطاها
    try:
        run_telegram_bot.start_polling()
    except Exception as e:
        logger.critical(f"Error starting bot: {str(e)}", exc_info=True)
        sys.exit(1)

except Exception as e:
    logger.critical(f"Fatal error: {str(e)}", exc_info=True)
    sys.exit(1)