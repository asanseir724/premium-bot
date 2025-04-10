#!/bin/bash

# تنظیمات رنگی برای پیام‌ها
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}نصب ربات مدیریت اشتراک تلگرام با روش جایگزین${NC}"
echo -e "${BLUE}=========================================${NC}"

# کلون مخزن از GitHub
echo -e "\n${YELLOW}[1/2] در حال دریافت کد از مخزن GitHub...${NC}"
REPO_DIR="premium-bot"
git clone https://github.com/asanseir724/premium-bot.git $REPO_DIR
if [ $? -ne 0 ]; then
  echo -e "${RED}خطا در دریافت کد از GitHub. لطفاً دسترسی به اینترنت را بررسی کنید.${NC}"
  exit 1
fi

# تغییر به دایرکتوری پروژه و اجرای اسکریپت نصب
echo -e "\n${YELLOW}[2/2] در حال اجرای اسکریپت نصب...${NC}"
cd $REPO_DIR
chmod +x install.sh
./install.sh

echo -e "\n${GREEN}فرآیند نصب جایگزین به پایان رسید.${NC}"
echo -e "${BLUE}=========================================${NC}"