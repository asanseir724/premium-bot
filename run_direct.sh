#!/bin/bash

# راه‌اندازی مستقیم ربات بدون نیاز به سرویس سیستمی
cd ~/premium-bot
gunicorn --bind 0.0.0.0:5000 --reload main:app