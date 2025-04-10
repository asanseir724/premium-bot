#!/bin/bash

# رنگ‌بندی خروجی
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}به‌روزرسانی ربات مدیریت اشتراک تلگرام${NC}"
echo -e "${BLUE}=========================================${NC}"

# بررسی وجود گیت
if ! command -v git &> /dev/null; then
    echo -e "${RED}گیت نصب نیست. در حال نصب...${NC}"
    apt-get update && apt-get install -y git
fi

# بررسی وجود فولدر .git
if [ ! -d ".git" ]; then
    echo -e "${RED}این پوشه یک مخزن گیت نیست. لطفاً با کلون کردن مخزن شروع کنید.${NC}"
    exit 1
fi

# ذخیره فایل .env
echo -e "\n${YELLOW}[1/4] ذخیره تنظیمات فعلی...${NC}"
if [ -f ".env" ]; then
    cp .env .env.backup
    echo -e "${GREEN}فایل .env پشتیبان‌گیری شد.${NC}"
else
    echo -e "${RED}فایل .env یافت نشد. ممکن است تنظیمات شما پس از به‌روزرسانی از بین برود.${NC}"
fi

# دریافت آخرین تغییرات
echo -e "\n${YELLOW}[2/4] دریافت آخرین تغییرات از مخزن گیت...${NC}"
git fetch origin
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse @{u})

if [ "$LOCAL" = "$REMOTE" ]; then
    echo -e "${GREEN}ربات شما در حال حاضر به‌روز است.${NC}"
else
    echo -e "${YELLOW}نسخه جدید یافت شد. در حال به‌روزرسانی...${NC}"
    git pull origin master
    
    # بازگرداندن فایل .env
    if [ -f ".env.backup" ]; then
        cp .env.backup .env
        echo -e "${GREEN}تنظیمات .env بازگردانده شد.${NC}"
    fi
    
    # نصب پکیج‌های جدید
    echo -e "\n${YELLOW}[3/4] نصب وابستگی‌های جدید...${NC}"
    pip3 install -r requirements.txt

    # میگریشن دیتابیس
    echo -e "\n${YELLOW}[4/4] به‌روزرسانی ساختار دیتابیس...${NC}"
    python3 -c "
    from app import app, db
    import models
    with app.app_context():
        db.create_all()
    print('ساختار دیتابیس به‌روزرسانی شد.')
    "
    
    # راه‌اندازی مجدد سرویس
    echo -e "\n${YELLOW}راه‌اندازی مجدد سرویس...${NC}"
    systemctl restart telegrambot
    
    echo -e "\n${GREEN}✅ ربات با موفقیت به‌روزرسانی شد!${NC}"
fi

echo -e "\n${BLUE}-------------------------------------------${NC}"
echo -e "${YELLOW}وضعیت سرویس:${NC} sudo systemctl status telegrambot"
echo -e "${YELLOW}مشاهده لاگ:${NC} sudo journalctl -u telegrambot -f"
echo -e "${BLUE}-------------------------------------------${NC}"