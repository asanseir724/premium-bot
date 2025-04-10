#!/bin/bash

# Color settings for messages
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}Starting Telegram Premium Subscription Bot Installation${NC}"
echo -e "${BLUE}=========================================${NC}"

# Set up environment and install prerequisites
echo -e "\n${YELLOW}[1/7] Installing prerequisites...${NC}"
apt-get update -y
apt-get install -y python3 python3-pip postgresql postgresql-contrib libpq-dev git ufw

# Set up necessary ports
echo -e "\n${YELLOW}[2/7] Setting up firewall and opening ports...${NC}"
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 5000/tcp
ufw allow 22/tcp
ufw --force enable

# Set up PostgreSQL database
echo -e "\n${YELLOW}[3/7] Setting up PostgreSQL database...${NC}"
# Check PostgreSQL service status and start if needed
systemctl start postgresql
systemctl enable postgresql

# Create user and database
sudo -u postgres psql -c "CREATE USER telegrambot WITH PASSWORD 'telegrambot';" || echo "User already exists"
sudo -u postgres psql -c "CREATE DATABASE telegrambot OWNER telegrambot;" || echo "Database already exists"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE telegrambot TO telegrambot;" || echo "Permissions already granted"

# Set DATABASE_URL environment variable
export DATABASE_URL="postgresql://telegrambot:telegrambot@localhost/telegrambot"
# Add to .bashrc for permanent access
echo 'export DATABASE_URL="postgresql://telegrambot:telegrambot@localhost/telegrambot"' >> ~/.bashrc

# Install Python packages
echo -e "\n${YELLOW}[4/7] Installing Python libraries...${NC}"
pip3 install flask flask-login flask-sqlalchemy psycopg2-binary pytelegrambotapi sqlalchemy requests telebot trafilatura gunicorn alembic email-validator werkzeug

# Create .env file
echo -e "\n${YELLOW}[5/7] Creating environment settings file...${NC}"
if [ ! -f ".env" ]; then
  echo "DATABASE_URL=postgresql://telegrambot:telegrambot@localhost/telegrambot" > .env
  echo "SESSION_SECRET=$(openssl rand -hex 32)" >> .env
  echo "NOWPAYMENTS_API_KEY=your-api-key-here" >> .env
  echo "TELEGRAM_BOT_TOKEN=your-bot-token-here" >> .env
  echo "WEB_ADMIN_USERNAME=admin" >> .env
  echo "WEB_ADMIN_PASSWORD=admin" >> .env
  echo -e "${GREEN}The .env file has been created. Please set your Telegram bot token and NowPayments API key.${NC}"
else
  echo -e "${YELLOW}The .env file already exists. No changes made.${NC}"
fi

# Migration and database structure creation
echo -e "\n${YELLOW}[6/7] Creating database structure...${NC}"
python3 -c "
from app import app, db
import models
with app.app_context():
    db.create_all()
    try:
        from models import AdminUser
        from werkzeug.security import generate_password_hash
        # Check if admin exists
        admin = db.session.query(AdminUser).filter_by(username='admin').first()
        if not admin:
            admin = AdminUser(username='admin', password_hash=generate_password_hash('admin'), is_super_admin=True)
            db.session.add(admin)
            db.session.commit()
            print('Admin user created: admin/admin')
    except Exception as e:
        print(f'Error checking or creating admin: {e}')
"

# Create systemd service for automatic bot execution
echo -e "\n${YELLOW}[7/7] Creating systemd service for automatic execution...${NC}"
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

echo -e "\n${GREEN}✅ Telegram Premium Subscription Bot installation completed successfully!${NC}"
echo -e "${BLUE}-------------------------------------------${NC}"
echo -e "${YELLOW}Admin Web Panel:${NC} http://YOUR_SERVER_IP:5000/admin"
echo -e "${YELLOW}Default username/password:${NC} admin/admin"
echo -e "${YELLOW}Service status:${NC} sudo systemctl status telegrambot"
echo -e "${YELLOW}View logs:${NC} sudo journalctl -u telegrambot -f"
echo -e "${BLUE}-------------------------------------------${NC}"
echo -e "${RED}Important: Please edit the .env file and set your Telegram bot token and NowPayments API key.${NC}"
echo -e "${GREEN}To run the bot in polling mode:${NC} python3 start_bot.py"
echo -e "${BLUE}=========================================${NC}"