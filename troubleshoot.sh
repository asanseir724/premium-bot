#!/bin/bash

# تنظیمات رنگی برای پیام‌ها
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}عیب‌یابی پنل مدیریت ربات تلگرام${NC}"
echo -e "${BLUE}=========================================${NC}"

# بررسی وضعیت سرویس
echo -e "\n${YELLOW}[1/5] بررسی وضعیت سرویس ربات...${NC}"
if systemctl is-active --quiet telegrambot; then
    echo -e "${GREEN}سرویس ربات در حال اجرا است.${NC}"
else
    echo -e "${RED}سرویس ربات اجرا نمی‌شود!${NC}"
    echo -e "${YELLOW}در حال تلاش برای راه‌اندازی مجدد...${NC}"
    sudo systemctl restart telegrambot
    sleep 3
    if systemctl is-active --quiet telegrambot; then
        echo -e "${GREEN}سرویس ربات با موفقیت راه‌اندازی شد.${NC}"
    else
        echo -e "${RED}راه‌اندازی سرویس با شکست مواجه شد. لاگ خطاها:${NC}"
        sudo journalctl -u telegrambot -n 20 --no-pager
    fi
fi

# بررسی فایروال
echo -e "\n${YELLOW}[2/5] بررسی تنظیمات فایروال...${NC}"
if command -v ufw &> /dev/null; then
    if ufw status | grep -q "Status: active"; then
        if ufw status | grep -q "5000.*ALLOW"; then
            echo -e "${GREEN}پورت 5000 در فایروال باز است.${NC}"
        else
            echo -e "${RED}پورت 5000 در فایروال مسدود است!${NC}"
            echo -e "${YELLOW}در حال باز کردن پورت...${NC}"
            sudo ufw allow 5000/tcp
            echo -e "${GREEN}پورت 5000 باز شد.${NC}"
        fi
    else
        echo -e "${YELLOW}فایروال UFW غیرفعال است.${NC}"
    fi
elif command -v firewalld &> /dev/null; then
    if firewall-cmd --state | grep -q "running"; then
        if firewall-cmd --list-ports | grep -q "5000/tcp"; then
            echo -e "${GREEN}پورت 5000 در فایروال باز است.${NC}"
        else
            echo -e "${RED}پورت 5000 در فایروال مسدود است!${NC}"
            echo -e "${YELLOW}در حال باز کردن پورت...${NC}"
            sudo firewall-cmd --add-port=5000/tcp --permanent
            sudo firewall-cmd --reload
            echo -e "${GREEN}پورت 5000 باز شد.${NC}"
        fi
    else
        echo -e "${YELLOW}فایروال firewalld غیرفعال است.${NC}"
    fi
else
    echo -e "${YELLOW}فایروال شناخته شده‌ای یافت نشد.${NC}"
fi

# بررسی اجرای فرآیند روی پورت 5000
echo -e "\n${YELLOW}[3/5] بررسی پروسه‌های در حال اجرا روی پورت 5000...${NC}"
if command -v netstat &> /dev/null; then
    if netstat -tlnp | grep -q ":5000"; then
        echo -e "${GREEN}یک پروسه روی پورت 5000 در حال اجراست:${NC}"
        netstat -tlnp | grep ":5000"
    else
        echo -e "${RED}هیچ پروسه‌ای روی پورت 5000 اجرا نمی‌شود!${NC}"
    fi
elif command -v ss &> /dev/null; then
    if ss -tlnp | grep -q ":5000"; then
        echo -e "${GREEN}یک پروسه روی پورت 5000 در حال اجراست:${NC}"
        ss -tlnp | grep ":5000"
    else
        echo -e "${RED}هیچ پروسه‌ای روی پورت 5000 اجرا نمی‌شود!${NC}"
    fi
else
    echo -e "${YELLOW}ابزار بررسی پورت یافت نشد.${NC}"
fi

# بررسی اتصال به پورت 5000
echo -e "\n${YELLOW}[4/5] آزمایش اتصال محلی به پورت 5000...${NC}"
if curl -s http://localhost:5000/ -o /dev/null -w "%{http_code}" | grep -q "2[0-9][0-9]\|3[0-9][0-9]"; then
    echo -e "${GREEN}اتصال محلی به وب‌سرور موفقیت‌آمیز بود.${NC}"
else
    echo -e "${RED}اتصال محلی به وب‌سرور ناموفق بود.${NC}"
fi

# بررسی آدرس IP
echo -e "\n${YELLOW}[5/5] آدرس IP سرور شما:${NC}"
if command -v curl &> /dev/null; then
    PUBLIC_IP=$(curl -s https://api.ipify.org)
    echo -e "${BLUE}آدرس IP عمومی:${NC} $PUBLIC_IP"
    echo -e "${BLUE}آدرس پنل مدیریت:${NC} http://$PUBLIC_IP:5000/admin"
else
    echo -e "${RED}ابزار curl برای تشخیص IP یافت نشد.${NC}"
fi

echo -e "\n${GREEN}عیب‌یابی به پایان رسید. لطفاً با استفاده از آدرس IP و پورت 5000 به پنل مدیریت دسترسی پیدا کنید.${NC}"
echo -e "${BLUE}نام کاربری و رمز عبور پیش‌فرض: admin/admin${NC}"
echo -e "${BLUE}=========================================${NC}"

# راه‌اندازی مجدد ربات به عنوان فرآیندی پیش‌زمینه
echo -e "\n${YELLOW}آیا می‌خواهید ربات را به صورت پیش‌زمینه اجرا کنید تا لاگ‌ها را ببینید؟ (y/n)${NC}"
read -r answer
if [[ "$answer" =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}توجه: برای خروج کلید CTRL+C را فشار دهید${NC}"
    cd ~/premium-bot
    gunicorn --bind 0.0.0.0:5000 --reload main:app
fi