# ربات مدیریت اشتراک تلگرام

یک سیستم پیشرفته مدیریت اشتراک تلگرام با قابلیت پرداخت رمزارز و پنل مدیریت جامع.

<div dir="rtl">

## ویژگی‌ها

- 🤖 ربات تلگرام با قابلیت مدیریت اشتراک‌های پرمیوم
- 💰 پشتیبانی از پرداخت رمزارزی از طریق NowPayments
- 👨‍💼 پنل مدیریت چند سطحی با ابزارهای مدیریتی جامع
- 📢 سیستم وبهوک و مدیریت اطلاع‌رسانی
- 🔐 مدیریت امن تنظیمات و توکن ربات
- 📱 سیستم اطلاع‌رسانی کانال عمومی برای اعلام‌های خرید
- ⚙️ مدیریت پیشرفته تنظیمات کانال‌ها با پشتیبانی از ID کانال عددی و نام کاربری
- 📋 گردش کاری بهبود یافته بررسی و مدیریت سفارش‌ها
- 🌐 API خارجی برای یکپارچه‌سازی با سیستم‌های دیگر

## نصب سریع

برای نصب و راه‌اندازی سریع ربات، کافیست دستور زیر را اجرا کنید:

```bash
chmod +x install.sh && ./install.sh
```

این اسکریپت تمام پیش‌نیازها را نصب می‌کند، دیتابیس را راه‌اندازی می‌کند، و سرویس مربوطه را ایجاد می‌کند.

## پیش‌نیازها

- Python 3.8+
- PostgreSQL
- پکیج‌های پایتون مورد نیاز (در فایل requirements.txt)
- توکن ربات تلگرام (از [@BotFather](https://t.me/BotFather))
- حساب NowPayments برای پذیرش پرداخت رمزارزی

## نصب دستی

1. کلون کردن مخزن:
```bash
git clone https://github.com/your-username/telegram-subscription-bot.git
cd telegram-subscription-bot
```

2. نصب پیش‌نیازها:
```bash
pip install -r requirements.txt
```

3. ایجاد فایل .env:
```bash
DATABASE_URL=postgresql://username:password@localhost/dbname
SESSION_SECRET=your-secret-key
NOWPAYMENTS_API_KEY=your-api-key
TELEGRAM_BOT_TOKEN=your-bot-token
```

4. راه‌اندازی دیتابیس:
```bash
python migrate.py
```

5. اجرای برنامه:
```bash
gunicorn --bind 0.0.0.0:5000 main:app
```

6. اجرای ربات تلگرام (در یک ترمینال دیگر):
```bash
python start_bot.py
```

## راه‌اندازی با Docker

1. ساخت ایمیج:
```bash
docker build -t telegram-subscription-bot .
```

2. اجرا:
```bash
docker run -d -p 5000:5000 --env-file .env --name telegram-bot telegram-subscription-bot
```

## ساختار برنامه

- `app.py`: تنظیمات اصلی برنامه Flask و دیتابیس
- `main.py`: نقطه ورود اصلی برنامه
- `models.py`: تعریف مدل‌های دیتابیس
- `run_telegram_bot.py`: منطق اصلی ربات تلگرام
- `api.py`: API خارجی برای یکپارچه‌سازی
- `nowpayments.py`: کلاینت API برای NowPayments
- `config_manager.py`: مدیریت تنظیمات برنامه
- `start_bot.py`: اسکریپت مستقل برای اجرای ربات در حالت polling

## پنل مدیریت

پنل مدیریت در آدرس `/admin` قابل دسترسی است. دسترسی پیش‌فرض:
- نام کاربری: admin
- رمز عبور: admin

## API خارجی

مستندات API در آدرس `/api/docs` قابل دسترسی است. API امکان ایجاد سفارش‌های اشتراک، بررسی وضعیت و لیست سفارش‌ها را فراهم می‌کند. مثال‌ها در پوشه `/static/examples/` قابل دسترسی هستند.

</div>

## نگهداری

### بررسی وضعیت سرویس
```bash
sudo systemctl status telegrambot
```

### مشاهده لاگ‌ها
```bash
sudo journalctl -u telegrambot -f
```

### راه‌اندازی مجدد
```bash
sudo systemctl restart telegrambot
```

## امنیت

- همیشه کلید‌های API و توکن‌ها را در فایل `.env` ذخیره کنید
- رمز عبور ادمین پیش‌فرض را تغییر دهید
- به ربات تلگرام دسترسی مدیر در کانال‌های مورد نظر بدهید
- تنظیمات فایروال را برای محدود کردن دسترسی به پورت‌ها انجام دهید

## پشتیبانی

برای پشتیبانی، لطفاً یک issue در گیت‌هاب ایجاد کنید یا با ایمیل در تماس باشید.

---

با افتخار توسعه داده شده برای مدیریت اشتراک‌های پرمیوم تلگرام 🚀