#!/usr/bin/env python3
"""
Standalone script to start the Telegram bot in polling mode.
This is independent of the web application and can be run separately.
"""

import logging
import sys
import os
import time

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("start_bot")

def main():
    """Main function to start the bot"""
    logger.info("Starting Telegram bot in polling mode")
    
    try:
        # Import the bot module and start polling
        from run_telegram_bot import start_polling, bot, config_manager
        
        # Check if bot token exists
        bot_token = config_manager.get_config_value("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            logger.error("No bot token found. Please set it in the admin panel or as an environment variable.")
            return 1
        
        # Enable the bot in config
        config_manager.set_config_value("bot_enabled", True)
        
        # Get bot info for verification
        try:
            bot_info = bot.get_me()
            logger.info(f"Connected to bot: @{bot_info.username} (ID: {bot_info.id})")
        except Exception as e:
            logger.error(f"Failed to connect to Telegram API: {e}")
            return 1
            
        # Start the bot
        logger.info("Starting bot polling...")
        start_polling()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        logger.exception(e)
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())