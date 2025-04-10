# Default subscription plans
SUBSCRIPTION_PLANS = [
    {
        "id": "plan_3month",
        "name": "3-Month Premium",
        "description": "Access Premium features for 3 months",
        "price": 10.99,
        "currency": "USD"
    },
    {
        "id": "plan_6month",
        "name": "6-Month Premium",
        "description": "Access Premium features for 6 months",
        "price": 19.99,
        "currency": "USD"
    },
    {
        "id": "plan_1year",
        "name": "1-Year Premium",
        "description": "Access Premium features for 1 year",
        "price": 34.99,
        "currency": "USD"
    }
]

# Bot settings
BOT_ADMINS = []  # List of Telegram user IDs who are admins
SUPPORT_CONTACT = "@support"  # Support contact username or link

# Channel settings
ADMIN_CHANNEL = ""  # Admin channel ID/username for notifications
PUBLIC_CHANNEL = ""  # Public channel ID/username for announcing purchases

# Payment settings
DEFAULT_CURRENCY = "USD"
PAYMENT_PROVIDER = "NowPayments"
ACCEPTED_CRYPTOCURRENCIES = ["TRX"]  # Default cryptocurrency
ORDER_EXPIRATION_HOURS = 24  # Hours until an order expires if not paid
