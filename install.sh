#!/bin/bash

# تنظیمات رنگی برای پیام‌ها
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}آغاز نصب ربات مدیریت اشتراک تلگرام${NC}"
echo -e "${BLUE}=========================================${NC}"

# تنظیم محیط و نصب پیش‌نیازها
echo -e "\n${YELLOW}[1/7] نصب پیش‌نیازها...${NC}"
apt-get update -y
apt-get install -y python3 python3-pip postgresql postgresql-contrib libpq-dev git ufw

# تنظیم پورت‌های مورد نیاز
echo -e "\n${YELLOW}[2/7] تنظیم فایروال و باز کردن پورت‌ها...${NC}"
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 5000/tcp
ufw allow 22/tcp
ufw --force enable

# تنظیم دیتابیس PostgreSQL
echo -e "\n${YELLOW}[3/7] تنظیم دیتابیس PostgreSQL...${NC}"
# بررسی وضعیت سرویس PostgreSQL و راه‌اندازی در صورت نیاز
systemctl start postgresql
systemctl enable postgresql

# ایجاد کاربر و دیتابیس
sudo -u postgres psql -c "CREATE USER telegrambot WITH PASSWORD 'telegrambot';" || echo "User already exists"
sudo -u postgres psql -c "CREATE DATABASE telegrambot OWNER telegrambot;" || echo "Database already exists"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE telegrambot TO telegrambot;" || echo "Permissions already granted"

# تنظیم DATABASE_URL متغیر محیطی
export DATABASE_URL="postgresql://telegrambot:telegrambot@localhost/telegrambot"
# اضافه کردن به .bashrc برای دسترسی دائم
echo 'export DATABASE_URL="postgresql://telegrambot:telegrambot@localhost/telegrambot"' >> ~/.bashrc

# نصب پکیج‌های پایتون 
echo -e "\n${YELLOW}[4/7] نصب کتابخانه‌های پایتون...${NC}"
pip3 install flask flask-login flask-sqlalchemy psycopg2-binary pytelegrambotapi sqlalchemy requests telebot trafilatura gunicorn alembic email-validator werkzeug

# ایجاد فایل .env
echo -e "\n${YELLOW}[5/7] ایجاد فایل تنظیمات محیطی...${NC}"
if [ ! -f ".env" ]; then
  echo "DATABASE_URL=postgresql://telegrambot:telegrambot@localhost/telegrambot" > .env
  echo "SESSION_SECRET=$(openssl rand -hex 32)" >> .env
  echo "NOWPAYMENTS_API_KEY=your-api-key-here" >> .env
  echo "TELEGRAM_BOT_TOKEN=your-bot-token-here" >> .env
  echo "WEB_ADMIN_USERNAME=admin" >> .env
  echo "WEB_ADMIN_PASSWORD=admin" >> .env
  echo -e "${GREEN}فایل .env ایجاد شد. لطفاً توکن ربات تلگرام و کلید API NowPayments را تنظیم کنید.${NC}"
else
  echo -e "${YELLOW}فایل .env موجود است. تغییری انجام نشد.${NC}"
fi

# میگریشن و ایجاد ساختار دیتابیس
echo -e "\n${YELLOW}[6/7] ایجاد ساختار دیتابیس...${NC}"
python3 -c "
from app import app, db
import models
with app.app_context():
    db.create_all()
    try:
        from models import AdminUser
        from werkzeug.security import generate_password_hash
        # بررسی وجود ادمین
        admin = db.session.query(AdminUser).filter_by(username='admin').first()
        if not admin:
            admin = AdminUser(username='admin', password_hash=generate_password_hash('admin'), is_super_admin=True)
            db.session.add(admin)
            db.session.commit()
            print('Admin user created: admin/admin')
    except Exception as e:
        print(f'Error checking or creating admin: {e}')
"

# ساخت سرویس systemd برای اجرای خودکار ربات
echo -e "\n${YELLOW}[7/7] ساخت سرویس systemd برای اجرای خودکار...${NC}"
echo "[Unit]
Description=Telegram Subscription Bot
After=network.target postgresql.service

[Service]
User=$(whoami)
WorkingDirectory=$(pwd)
Environment=DATABASE_URL=postgresql://telegrambot:telegrambot@localhost/telegrambot
ExecStart=$(which gunicorn) --bind 0.0.0.0:5000 --workers 4 main:app
Restart=always

[Install]
WantedBy=multi-user.target" | sudo tee /etc/systemd/system/telegrambot.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable telegrambot.service
sudo systemctl start telegrambot.service

echo -e "\n${GREEN}✅ نصب ربات مدیریت اشتراک تلگرام با موفقیت انجام شد!${NC}"
echo -e "${BLUE}-------------------------------------------${NC}"
echo -e "${YELLOW}وب پنل ادمین:${NC} http://YOUR_SERVER_IP:5000/admin"
echo -e "${YELLOW}نام کاربری/رمز عبور پیش‌فرض:${NC} admin/admin"
echo -e "${YELLOW}وضعیت سرویس:${NC} sudo systemctl status telegrambot"
echo -e "${YELLOW}مشاهده لاگ:${NC} sudo journalctl -u telegrambot -f"
echo -e "${BLUE}-------------------------------------------${NC}"
echo -e "${RED}مهم: لطفاً فایل .env را ویرایش کرده و توکن ربات تلگرام و API NowPayments را تنظیم کنید.${NC}"
echo -e "${GREEN}برای اجرای ربات در حالت پولینگ:${NC} python3 start_bot.py"
echo -e "${BLUE}=========================================${NC}"