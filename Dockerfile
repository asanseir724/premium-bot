FROM python:3.11-slim

# تنظیم متغیرهای محیطی
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# نصب پیش‌نیازها
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ایجاد پوشه کاری  
WORKDIR /app

# کپی کردن فایل requirements
COPY requirements.txt .

# نصب پکیج‌های پایتون
RUN pip install --no-cache-dir -r requirements.txt

# کپی کردن کد برنامه
COPY . .

# افشای پورت
EXPOSE 5000

# اجرای میگریشن و سپس برنامه
CMD python -c "from app import app, db; import models; with app.app_context(): db.create_all()" && \
    gunicorn --bind 0.0.0.0:5000 --workers 4 main:app