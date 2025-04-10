# Development Guide

This document provides detailed information for developers who want to contribute to or extend the Telegram Premium Subscription Bot.

## Environment Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
   - Copy `.env.example` to `.env`
   - Obtain a Telegram bot token from [@BotFather](https://t.me/BotFather)
   - Get an API key from [NowPayments](https://nowpayments.io/)
   - Configure your PostgreSQL database credentials

## Database Schema

The application uses SQLAlchemy ORM with the following main models:

### User
Represents a Telegram user who interacts with the bot.
- `id`: Primary key
- `telegram_id`: Unique Telegram user ID
- `username`: Telegram username
- `first_name`: User's first name
- `last_name`: User's last name
- `created_at`: Timestamp when the user was first registered
- `updated_at`: Timestamp when the user was last updated

### Order
Represents a subscription order.
- `id`: Primary key
- `order_id`: Unique 5-digit order ID
- `user_id`: Foreign key to User
- `plan_id`: Subscription plan identifier
- `plan_name`: Name of the selected plan
- `amount`: Order amount
- `currency`: Currency code (default: USD)
- `status`: Order status (enum: pending, awaiting_payment, etc.)
- `telegram_username`: Username to activate Premium for
- `admin_notes`: Notes from admin about the order
- `payment_id`: Associated payment ID
- `payment_url`: URL for payment
- `activation_link`: Link for activating the subscription
- `created_at`: Order creation timestamp
- `updated_at`: Last update timestamp
- `expires_at`: Order expiration timestamp

### PaymentTransaction
Represents a payment transaction.
- `id`: Primary key
- `payment_id`: Unique payment identifier
- `order_id`: Foreign key to Order
- `amount`: Payment amount
- `currency`: Currency code
- `pay_currency`: Cryptocurrency used for payment
- `status`: Payment status
- `ipn_data`: Instant Payment Notification data
- `created_at`: Transaction creation timestamp
- `updated_at`: Last update timestamp
- `completed_at`: Completion timestamp

## Application Architecture

### Core Components

1. **Bot Module** (`run_telegram_bot.py`):
   - Handles user interactions and commands
   - Processes button callbacks
   - Manages admin panel functionality

2. **Web Interface** (`main.py`):
   - Provides administrative dashboard
   - Displays payment and order information
   - Manages webhook endpoints for payment notifications

3. **Database Layer** (`models.py`):
   - Defines database schema and relationships
   - Handles data persistence

4. **Payment Integration** (`nowpayments.py`):
   - Interfaces with the NowPayments API
   - Handles payment creation and verification
   - Processes payment notifications

5. **Configuration Management** (`config_manager.py`):
   - Manages configuration with refresh capability
   - Provides access to subscription plans and settings

### Workflow

1. **User Flow**:
   - User starts the bot with `/start`
   - Bot displays available subscription plans
   - User selects a plan
   - User provides Telegram username to activate Premium for
   - User receives a payment link
   - After payment, user confirms payment in the bot
   - Admin reviews the payment and approves/rejects
   - User receives notification of the result

2. **Admin Flow**:
   - Admin accesses the panel with `/admin`
   - Admin can view pending orders
   - Admin can approve/reject orders
   - Admin can edit subscription plans
   - Admin can manage support settings
   - Super Admin can manage other admins

## Extension Points

### Adding New Subscription Plans

Modify `config.py` to add new subscription plans:

```python
SUBSCRIPTION_PLANS = [
    {
        "id": "plan_3month",
        "name": "3-Month Premium",
        "description": "Access Premium features for 3 months",
        "price": 10.99,
        "payment_link": "https://nowpayments.io/payment/?iid=XXXXX"
    },
    # Add new plans here
]
```

### Adding New Payment Methods

To add new payment methods or cryptocurrencies:

1. Update `nowpayments.py` to support the new payment method
2. Add UI elements in the bot to show the new payment option
3. Handle the payment processing for the new method

### Adding New Admin Features

To add new features to the admin panel:

1. Define new handler functions in `run_telegram_bot.py`
2. Create new menu options and callbacks
3. Implement the functionality

## Testing

### Automated Tests

Run the automated tests:

```bash
python -m unittest discover tests
```

### Manual Testing

For manual testing, you can use the following procedures:

1. **Testing the Bot**:
   - Start a conversation with your bot
   - Test each command: `/start`, `/plans`, `/help`, `/support`, `/admin`
   - Go through the subscription purchase flow
   - Test admin approval/rejection

2. **Testing Payments**:
   - Use test mode in NowPayments
   - Verify payment creation and confirmation
   - Test IPN (Instant Payment Notification) handling

## Deployment

### Production Setup

For production deployment:

1. Use a production-grade WSGI server like Gunicorn
2. Set up proper database connection pooling
3. Configure webhook URL in the Telegram Bot API
4. Ensure secure HTTPS endpoints for webhooks
5. Consider using a process manager like Supervisor

### Webhook Configuration

Configure the webhook for Telegram bot:

```bash
curl -F "url=https://yourdomain.com/webhook" https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook
```

### Database Migrations

For database schema changes:

1. Create a migration script
2. Test migration on a staging database
3. Apply migration to production with appropriate backups

## Common Issues and Solutions

### Bot Not Responding

1. Check if the bot is running
2. Verify your Telegram bot token
3. Check the logs for errors
4. Ensure proper internet connectivity

### Payment Issues

1. Verify NowPayments API key
2. Check webhook configuration
3. Review payment logs
4. Test with small amounts

### Database Connectivity

1. Verify database credentials
2. Check network connectivity to the database
3. Ensure proper database privileges
4. Review connection pool settings

## Code Style and Guidelines

- Follow PEP 8
- Write descriptive comments
- Use meaningful variable and function names
- Document public APIs and complex functionality
- Write unit tests for new features