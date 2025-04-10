#!/bin/bash

# تنظیمات رنگی برای پیام‌ها
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}راه‌اندازی ربات تلگرام در حالت پولینگ${NC}"
echo -e "${BLUE}=========================================${NC}"

# بررسی پوشه پروژه
if [ ! -d "$HOME/premium-bot" ]; then
    echo -e "${RED}خطا: پوشه پروژه یافت نشد!${NC}"
    echo -e "${YELLOW}آیا می‌خواهید مخزن را کلون کنید؟ (y/n)${NC}"
    read -r answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        cd $HOME
        git clone https://github.com/asanseir724/premium-bot.git
        echo -e "${GREEN}مخزن با موفقیت کلون شد.${NC}"
    else
        echo -e "${RED}لطفاً ابتدا مخزن را کلون کنید.${NC}"
        exit 1
    fi
fi

# حرکت به پوشه پروژه
cd $HOME/premium-bot

# بررسی وجود فایل start_bot.py
if [ ! -f "start_bot.py" ]; then
    echo -e "${RED}فایل start_bot.py یافت نشد!${NC}"
    exit 1
fi

# تنظیم توکن ربات تلگرام اگر در فایل .env موجود نیست
if [ ! -f ".env" ] || ! grep -q "TELEGRAM_BOT_TOKEN" .env; then
    echo -e "\n${YELLOW}توکن ربات تلگرام خود را وارد کنید:${NC}"
    read -r token
    if [ -n "$token" ]; then
        if [ ! -f ".env" ]; then
            echo "TELEGRAM_BOT_TOKEN=$token" > .env
        else
            sed -i '/TELEGRAM_BOT_TOKEN=/d' .env
            echo "TELEGRAM_BOT_TOKEN=$token" >> .env
        fi
        echo -e "${GREEN}توکن ربات با موفقیت تنظیم شد.${NC}"
    else
        echo -e "${RED}توکن نامعتبر. لطفاً یک توکن معتبر وارد کنید.${NC}"
        exit 1
    fi
fi

# نصب نیازمندی‌ها
echo -e "\n${YELLOW}بررسی و نصب نیازمندی‌ها...${NC}"
pip3 install -r requirements.txt 2>/dev/null || pip3 install pytelegrambotapi telebot requests

# اجرای ربات در حالت پولینگ
echo -e "\n${GREEN}در حال راه‌اندازی ربات در حالت پولینگ...${NC}"
echo -e "${YELLOW}توجه: این فرآیند در پس‌زمینه اجرا می‌شود.${NC}"
echo -e "${YELLOW}برای مشاهده لاگ‌ها: tail -f bot_polling.log${NC}"
echo -e "${YELLOW}برای توقف ربات: pkill -f start_bot.py${NC}"

# اجرای ربات در پس‌زمینه و ذخیره لاگ‌ها
nohup python3 start_bot.py > bot_polling.log 2>&1 &

echo -e "\n${GREEN}ربات با موفقیت در حالت پولینگ راه‌اندازی شد.${NC}"
echo -e "${BLUE}ربات شما اکنون با نام کاربری تنظیم شده در فایل .env، به پیام‌ها پاسخ می‌دهد.${NC}"
echo -e "${BLUE}=========================================${NC}"

# نمایش لاگ‌های اخیر
sleep 2
echo -e "\n${YELLOW}لاگ‌های اخیر:${NC}"
tail -n 10 bot_polling.log