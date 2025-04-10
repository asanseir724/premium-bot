#!/bin/bash

# تنظیمات رنگی برای پیام‌ها
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}راه‌اندازی HTTPS برای ربات تلگرام${NC}"
echo -e "${BLUE}=========================================${NC}"

# نصب Nginx و ابزارهای SSL
echo -e "\n${YELLOW}[1/5] نصب Nginx و ابزارهای مورد نیاز...${NC}"
apt-get update -y
apt-get install -y nginx certbot openssl

# ایجاد گواهی خودامضا
echo -e "\n${YELLOW}[2/5] ایجاد گواهی خودامضا...${NC}"
CERT_DIR="/etc/nginx/ssl"
mkdir -p $CERT_DIR

if [ ! -f "$CERT_DIR/telegram-bot.key" ]; then
    # ایجاد گواهی خودامضا
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout $CERT_DIR/telegram-bot.key \
      -out $CERT_DIR/telegram-bot.crt \
      -subj "/CN=*"
    echo -e "${GREEN}گواهی SSL خودامضا ایجاد شد.${NC}"
else
    echo -e "${YELLOW}گواهی SSL از قبل وجود دارد.${NC}"
fi

# دریافت آدرس IP عمومی
PUBLIC_IP=$(curl -s https://api.ipify.org)
echo -e "\n${YELLOW}[3/5] آدرس IP عمومی شما: ${PUBLIC_IP}${NC}"

# ایجاد پیکربندی Nginx
echo -e "\n${YELLOW}[4/5] ایجاد پیکربندی Nginx...${NC}"
cat > /etc/nginx/sites-available/telegram-bot <<EOF
server {
    listen 80;
    server_name $PUBLIC_IP;
    
    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name $PUBLIC_IP;

    ssl_certificate $CERT_DIR/telegram-bot.crt;
    ssl_certificate_key $CERT_DIR/telegram-bot.key;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/telegram-bot /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# بررسی پیکربندی و راه‌اندازی مجدد Nginx
nginx -t
if [ $? -eq 0 ]; then
    echo -e "${GREEN}پیکربندی Nginx با موفقیت تأیید شد.${NC}"
    systemctl restart nginx
    echo -e "${GREEN}Nginx مجددا راه‌اندازی شد.${NC}"
else
    echo -e "${RED}خطا در پیکربندی Nginx. لطفا مشکل را رفع کنید.${NC}"
    exit 1
fi

# تنظیم وب‌هوک تلگرام
echo -e "\n${YELLOW}[5/5] راه‌اندازی وب‌هوک تلگرام...${NC}"
echo -e "${BLUE}برای تنظیم وب‌هوک تلگرام، از آدرس زیر استفاده کنید:${NC}"
echo -e "${GREEN}https://$PUBLIC_IP/telegram-webhook${NC}"

echo -e "\n${YELLOW}توجه: این گواهی خودامضا است و ممکن است تلگرام آن را نپذیرد.${NC}"
echo -e "${YELLOW}برای استفاده از وب‌هوک تلگرام، ترجیحاً از یک دامنه با گواهی معتبر استفاده کنید.${NC}"

echo -e "\n${YELLOW}برای تنظیم دستی وب‌هوک در ربات تلگرام، این دستورات را اجرا کنید:${NC}"
echo -e "cd ~/premium-bot"
echo -e "python3 -c \"import run_telegram_bot; run_telegram_bot.set_webhook('https://$PUBLIC_IP/telegram-webhook')\""

echo -e "\n${GREEN}راه‌اندازی HTTPS به پایان رسید.${NC}"
echo -e "${BLUE}پنل مدیریت اکنون در آدرس زیر قابل دسترسی است:${NC}"
echo -e "${GREEN}https://$PUBLIC_IP/admin${NC}"
echo -e "${BLUE}=========================================${NC}"

# روش استفاده از حالت پولینگ به جای وب‌هوک
echo -e "\n${YELLOW}روش جایگزین: استفاده از حالت پولینگ به جای وب‌هوک${NC}"
echo -e "اگر با خطا در تنظیم وب‌هوک مواجه شدید، می‌توانید از حالت پولینگ استفاده کنید:"
echo -e "cd ~/premium-bot"
echo -e "python3 start_bot.py"
echo -e "${BLUE}=========================================${NC}"