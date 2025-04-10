# راهنمای نصب سریع ربات مدیریت اشتراک تلگرام

<div dir="rtl">

این راهنما به شما کمک می‌کند تا ربات مدیریت اشتراک تلگرام را به سرعت نصب و راه‌اندازی کنید، حتی اگر دانش برنامه‌نویسی نداشته باشید.

## پیش‌نیازها

- یک سرور لینوکس با دسترسی SSH (ترجیحاً Ubuntu 20.04 یا بالاتر)
- دسترسی root یا sudo به سرور
- توکن ربات تلگرام (از [@BotFather](https://t.me/BotFather) دریافت کنید)
- یک حساب کاربری در [NowPayments.io](https://nowpayments.io) برای دریافت API Key (اختیاری)

## نصب سریع (یک خط)

فقط کافیست دستور زیر را در ترمینال سرور خود وارد کنید:

```bash
wget -O install.sh https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/telegram-premium-bot/master/install.sh && chmod +x install.sh && ./install.sh
```

(دستور بالا را با نام کاربری GitHub خود جایگزین کنید)

## مراحل نصب (با جزئیات)

اگر می‌خواهید مراحل نصب را با جزئیات بیشتری انجام دهید، مراحل زیر را دنبال کنید:

### 1. دریافت کد از GitHub

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/telegram-premium-bot.git
cd telegram-premium-bot
```

### 2. اجرای اسکریپت نصب

```bash
chmod +x install.sh
./install.sh
```

### 3. ویرایش فایل تنظیمات

اسکریپت نصب یک فایل `.env` ایجاد می‌کند. این فایل را باید ویرایش کنید و توکن ربات تلگرام و سایر تنظیمات را تغییر دهید:

```bash
nano .env
```

حداقل باید موارد زیر را تنظیم کنید:
- `TELEGRAM_BOT_TOKEN`: توکن ربات تلگرام شما
- `NOWPAYMENTS_API_KEY`: API Key سرویس NowPayments (اختیاری)
- `WEB_ADMIN_PASSWORD`: رمز عبور پنل مدیریت (پیش‌فرض: admin)

### 4. راه‌اندازی ربات

پس از نصب، سرویس ربات به صورت خودکار راه‌اندازی می‌شود. با دستورات زیر می‌توانید وضعیت آن را بررسی کنید:

```bash
# مشاهده وضعیت سرویس
sudo systemctl status telegrambot

# مشاهده لاگ‌ها
sudo journalctl -u telegrambot -f

# راه‌اندازی مجدد سرویس
sudo systemctl restart telegrambot
```

## دسترسی به پنل مدیریت

پنل مدیریت وب در آدرس زیر قابل دسترسی است:

```
http://YOUR_SERVER_IP:5000/admin
```

دسترسی پیش‌فرض:
- نام کاربری: admin
- رمز عبور: admin (در فایل .env قابل تغییر است)

## تنظیمات پیشرفته

### استفاده با Docker (اختیاری)

برای اجرا با Docker:

```bash
# نصب Docker (اگر نصب نیست)
curl -fsSL https://get.docker.com | sh
sudo systemctl start docker
sudo systemctl enable docker

# نصب Docker Compose
sudo apt install -y docker-compose

# اجرای برنامه
docker-compose up -d
```

### تنظیم وبهوک تلگرام (اختیاری)

اگر می‌خواهید از حالت وبهوک به جای polling استفاده کنید، باید مراحل زیر را انجام دهید:

1. یک دامنه یا ساب‌دامنه با SSL تنظیم کنید
2. به پنل مدیریت وارد شوید
3. به بخش تنظیمات ربات بروید
4. آدرس وبهوک را به صورت `https://YOUR_DOMAIN/telegram_webhook` وارد کنید
5. روی "تنظیم وبهوک" کلیک کنید

## عیب‌یابی رایج

### ربات پاسخ نمی‌دهد

1. وضعیت سرویس را بررسی کنید:
```bash
sudo systemctl status telegrambot
```

2. لاگ‌ها را بررسی کنید:
```bash
sudo journalctl -u telegrambot -f
```

3. مطمئن شوید توکن ربات در فایل `.env` درست تنظیم شده است

### خطای دیتابیس

1. وضعیت سرویس PostgreSQL را بررسی کنید:
```bash
sudo systemctl status postgresql
```

2. مطمئن شوید کاربر و دیتابیس به درستی ایجاد شده‌اند:
```bash
sudo -u postgres psql -c "\l"
sudo -u postgres psql -c "\du"
```

## پشتیبانی

برای کمک بیشتر، می‌توانید یک issue در GitHub ایجاد کنید یا با ایمیل با ما در تماس باشید.

---

موفق باشید! 🚀

</div>