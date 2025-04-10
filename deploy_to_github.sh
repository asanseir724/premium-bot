#!/bin/bash

# رنگ‌بندی خروجی
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}انتقال کد به GitHub${NC}"
echo -e "${BLUE}=========================================${NC}"

# دریافت توکن گیت‌هاب
if [ -z "$1" ]; then
  echo -e "${YELLOW}لطفاً توکن گیت‌هاب را وارد کنید:${NC}"
  read GITHUB_TOKEN
else
  GITHUB_TOKEN=$1
fi

# دریافت نام مخزن
if [ -z "$2" ]; then
  echo -e "${YELLOW}نام مخزن را وارد کنید (پیش‌فرض: telegram-premium-bot):${NC}"
  read -e -i "telegram-premium-bot" REPO_NAME
  REPO_NAME=${REPO_NAME:-telegram-premium-bot}
else
  REPO_NAME=$2
fi

# دریافت نام کاربری گیت‌هاب
if [ -z "$3" ]; then
  echo -e "${YELLOW}نام کاربری گیت‌هاب را وارد کنید:${NC}"
  read GITHUB_USERNAME
else
  GITHUB_USERNAME=$3
fi

# ایجاد مخزن گیت‌هاب جدید
echo -e "\n${YELLOW}[1/5] ایجاد مخزن گیت‌هاب...${NC}"
curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" \
     -d "{\"name\":\"$REPO_NAME\", \"description\":\"ربات مدیریت اشتراک تلگرام\", \"private\":true}" \
     "https://api.github.com/user/repos"

if [ $? -ne 0 ]; then
  echo -e "${RED}خطا در ایجاد مخزن گیت‌هاب. لطفاً توکن و نام کاربری را بررسی کنید.${NC}"
  exit 1
fi

# ایجاد فایل .gitignore
echo -e "\n${YELLOW}[2/5] ایجاد فایل‌های گیت...${NC}"
echo "
# بایت کامپایل شده پایتون
__pycache__/
*.py[cod]
*$py.class

# توزیع پایتون / بسته‌بندی
.Python
env/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# فایل‌های محیطی
.env
.venv
env/
venv/
ENV/
.env.local

# لاگ‌ها
logs/
*.log

# پوشه‌های سیستمی
.DS_Store
.idea/
.vscode/

# دیتابیس‌ها
*.sqlite
*.db

# پوشه دیپلوی
deploy/
deploy.zip

# گواهی‌نامه‌ها و کلیدها
*.pem
*.key
*.crt" > .gitignore

# آماده‌سازی مخزن محلی و ارسال به گیت‌هاب
echo -e "\n${YELLOW}[3/5] آماده‌سازی مخزن گیت محلی...${NC}"
git init
git add .
git config --local user.email "your-email@example.com"
git config --local user.name "$GITHUB_USERNAME"
git commit -m "نسخه اولیه ربات مدیریت اشتراک تلگرام"

echo -e "\n${YELLOW}[4/5] تنظیم مخزن ریموت...${NC}"
git remote add origin https://$GITHUB_TOKEN@github.com/$GITHUB_USERNAME/$REPO_NAME.git

echo -e "\n${YELLOW}[5/5] ارسال کد به GitHub...${NC}"
git push -u origin master

# نمایش اطلاعات
echo -e "\n${GREEN}✅ کد با موفقیت به GitHub ارسال شد!${NC}"
echo -e "${BLUE}-------------------------------------------${NC}"
echo -e "${YELLOW}آدرس مخزن:${NC} https://github.com/$GITHUB_USERNAME/$REPO_NAME"
echo -e "${YELLOW}برای کلون کردن:${NC} git clone https://github.com/$GITHUB_USERNAME/$REPO_NAME.git"
echo -e "${BLUE}-------------------------------------------${NC}"
echo -e "${GREEN}برای نصب ربات روی سرور، دستور زیر را اجرا کنید:${NC}"
echo -e "wget -O install.sh https://raw.githubusercontent.com/$GITHUB_USERNAME/$REPO_NAME/master/install.sh && chmod +x install.sh && ./install.sh"
echo -e "${BLUE}=========================================${NC}"