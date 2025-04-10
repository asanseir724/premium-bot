import os
import logging
import random
import string
import telebot
from telebot import types
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

# Set up detailed logging
import os
from logging.handlers import RotatingFileHandler
import traceback
import sys

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # Console handler
        logging.StreamHandler(),
        # File handler with rotation
        RotatingFileHandler(
            'logs/telegram_bot.log',
            maxBytes=10485760,  # 10MB
            backupCount=5
        )
    ]
)

# Get logger for this module
logger = logging.getLogger(__name__)

# Also log all telebot logs
telebot_logger = logging.getLogger('telebot')
telebot_logger.setLevel(logging.DEBUG)

# Handle uncaught exceptions
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        # Don't log keyboard interrupt
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

# Install exception handler
sys.excepthook = handle_exception

logger.info("Starting Telegram bot application")

# Import application components
from config import ORDER_EXPIRATION_HOURS
import config_manager
from nowpayments import NowPayments
from models import User, Order, PaymentTransaction

# Initialize bot with token from config or environment variable
BOT_TOKEN = config_manager.get_config_value("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("No bot token provided. Set the TELEGRAM_BOT_TOKEN environment variable or configure it in admin panel.")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# Initialize NowPayments API client
nowpayments_api = NowPayments(os.environ.get("NOWPAYMENTS_API_KEY"))

# Database setup
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///telegram_premium.db")
engine = create_engine(DATABASE_URL)
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

# Helper functions
def generate_order_id():
    """Generate a random 5-digit order ID"""
    return ''.join(random.choices(string.digits, k=5))

def get_or_create_user(message):
    """Get or create user from message"""
    telegram_id = str(message.from_user.id)
    user = db_session.query(User).filter_by(telegram_id=telegram_id).first()
    
    if not user:
        user = User(
            telegram_id=telegram_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
        db_session.add(user)
        db_session.commit()
        logger.info(f"Created new user: {user.username}")
    else:
        # Update user info if needed
        if user.username != message.from_user.username or \
           user.first_name != message.from_user.first_name or \
           user.last_name != message.from_user.last_name:
            user.username = message.from_user.username
            user.first_name = message.from_user.first_name
            user.last_name = message.from_user.last_name
            user.updated_at = datetime.utcnow()
            db_session.commit()
            logger.info(f"Updated user: {user.username}")
            
    return user

def is_admin(user_id):
    """Check if user is an admin"""
    admin_ids = config_manager.get_bot_admins()
    return str(user_id) in admin_ids

def create_main_menu():
    """Create the main menu markup"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    plans_button = types.InlineKeyboardButton("📱 Subscription Plans", callback_data="show_plans")
    help_button = types.InlineKeyboardButton("❓ Help", callback_data="help")
    support_button = types.InlineKeyboardButton("🆘 Support", callback_data="support")
    
    markup.add(plans_button, help_button, support_button)
    
    return markup

def create_plans_menu():
    """Create the subscription plans menu"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    plans = config_manager.get_subscription_plans()
    for plan in plans:
        button_text = f"{plan['name']} - ${plan['price']}"
        button = types.InlineKeyboardButton(button_text, callback_data=f"select_plan:{plan['id']}")
        markup.add(button)
    
    back_button = types.InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")
    markup.add(back_button)
    
    return markup

def create_admin_menu():
    """Create the admin menu markup"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    pending_orders = db_session.query(Order).filter_by(status="ADMIN_REVIEW").count()
    orders_button = types.InlineKeyboardButton(f"📦 Orders ({pending_orders})", callback_data="admin_orders")
    plans_button = types.InlineKeyboardButton("🏷️ Plans", callback_data="admin_plans")
    support_button = types.InlineKeyboardButton("🆘 Support", callback_data="admin_support")
    admins_button = types.InlineKeyboardButton("👨‍💼 Admins", callback_data="admin_admins")
    
    markup.add(orders_button, plans_button)
    markup.add(support_button, admins_button)
    
    return markup

def create_order_confirmation(plan):
    """Create order confirmation markup"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    confirm_button = types.InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_plan:{plan['id']}")
    cancel_button = types.InlineKeyboardButton("❌ Cancel", callback_data="show_plans")
    
    markup.add(confirm_button, cancel_button)
    
    return markup

# Bot command handlers
@bot.message_handler(commands=['start'])
def handle_start(message):
    user = get_or_create_user(message)
    
    # Welcome message
    welcome_text = (
        f"Hello, {message.from_user.first_name}! 👋\n\n"
        "Welcome to the Telegram Premium Subscription Bot.\n"
        "You can purchase Telegram Premium subscriptions using cryptocurrency.\n\n"
        "Please select an option from the menu below:"
    )
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_menu())

@bot.message_handler(commands=['plans'])
def handle_plans(message):
    plans = config_manager.get_subscription_plans()
    
    # Prepare plans message
    plans_text = "📱 *Available Subscription Plans*\n\n"
    
    for plan in plans:
        plans_text += f"🔹 *{plan['name']}* - ${plan['price']}\n"
        plans_text += f"{plan['description']}\n\n"
    
    plans_text += "Select a plan to proceed with your purchase:"
    
    bot.send_message(message.chat.id, plans_text, parse_mode="Markdown", reply_markup=create_plans_menu())

@bot.message_handler(commands=['help'])
def handle_help(message):
    help_text = (
        "📚 *Telegram Premium Subscription Bot Help*\n\n"
        "This bot allows you to purchase Telegram Premium subscriptions using cryptocurrency.\n\n"
        "*Available Commands:*\n"
        "/start - Start the bot and see the main menu\n"
        "/plans - View available subscription plans\n"
        "/help - Show this help message\n"
        "/support - Contact support\n"
        "/admin - Access admin panel (for admins only)\n\n"
        "*How to Purchase a Subscription:*\n"
        "1. Select a subscription plan\n"
        "2. Provide the Telegram username for activation\n"
        "3. Complete the payment using cryptocurrency\n"
        "4. Wait for confirmation from our team\n"
        "5. Receive your Premium activation link\n\n"
        "If you have any questions, use the /support command to contact our team."
    )
    
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['support'])
def handle_support(message):
    support_contact = config_manager.get_support_contact()
    
    support_text = (
        "🆘 *Need Help?*\n\n"
        f"Please contact our support team at {support_contact}.\n\n"
        "We're here to assist you with any questions or issues you may have regarding your Telegram Premium subscription purchase."
    )
    
    bot.send_message(message.chat.id, support_text, parse_mode="Markdown")

@bot.message_handler(commands=['admin'])
def handle_admin(message):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        admin_text = (
            "👨‍💼 *Admin Panel*\n\n"
            "Welcome to the admin panel. Please select an option below:"
        )
        
        bot.send_message(message.chat.id, admin_text, parse_mode="Markdown", reply_markup=create_admin_menu())
    else:
        bot.send_message(message.chat.id, "⛔ You don't have permission to access the admin panel.")

# Callback query handlers
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    if call.data == "show_plans":
        bot.edit_message_text(
            "📱 *Available Subscription Plans*\n\nSelect a plan to proceed with your purchase:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=create_plans_menu()
        )
    
    elif call.data == "back_to_main":
        bot.edit_message_text(
            "Welcome to the Telegram Premium Subscription Bot.\nPlease select an option from the menu below:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_main_menu()
        )
    
    elif call.data == "help":
        handle_help(call.message)
        
    elif call.data == "support":
        handle_support(call.message)
    
    elif call.data.startswith("select_plan:"):
        plan_id = call.data.split(":")[1]
        plan = config_manager.get_plan_by_id(plan_id)
        
        if plan:
            plan_details = (
                f"📱 *{plan['name']}*\n\n"
                f"💰 Price: ${plan['price']}\n"
                f"📝 Description: {plan['description']}\n\n"
                "Please confirm your selection to proceed with the purchase."
            )
            
            bot.edit_message_text(
                plan_details,
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=create_order_confirmation(plan)
            )
    
    elif call.data.startswith("confirm_plan:"):
        plan_id = call.data.split(":")[1]
        plan = config_manager.get_plan_by_id(plan_id)
        
        if plan:
            # Store the selected plan in user state
            bot.answer_callback_query(call.id, "Plan selected!")
            
            # Ask for username
            username_request = (
                "Please enter the Telegram username (with @) for which you want to activate Premium:\n\n"
                "For example: @username"
            )
            
            # Save plan info in a temporary way
            sent_msg = bot.edit_message_text(
                username_request,
                call.message.chat.id,
                call.message.message_id
            )
            
            # Register the next step handler
            bot.register_next_step_handler(sent_msg, process_username_step, plan_id=plan_id)
    
    # Admin callbacks
    elif call.data == "admin_orders":
        user_id = call.from_user.id
        
        if is_admin(user_id):
            # Get pending orders
            pending_orders = db_session.query(Order).filter_by(status="ADMIN_REVIEW").all()
            
            if pending_orders:
                orders_text = "📦 *Pending Orders*\n\n"
                
                markup = types.InlineKeyboardMarkup(row_width=1)
                
                for order in pending_orders:
                    orders_text += f"Order #{order.order_id} - {order.plan_name}\n"
                    orders_text += f"User: {order.telegram_username}\n"
                    orders_text += f"Amount: ${order.amount}\n"
                    orders_text += f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
                    
                    order_button = types.InlineKeyboardButton(
                        f"Review Order #{order.order_id}",
                        callback_data=f"review_order:{order.order_id}"
                    )
                    markup.add(order_button)
                
                back_button = types.InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="back_to_admin")
                markup.add(back_button)
                
                bot.edit_message_text(
                    orders_text,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
            else:
                markup = types.InlineKeyboardMarkup()
                back_button = types.InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="back_to_admin")
                markup.add(back_button)
                
                bot.edit_message_text(
                    "📦 *Pending Orders*\n\nNo pending orders at the moment.",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
    
    elif call.data.startswith("review_order:"):
        user_id = call.from_user.id
        
        if is_admin(user_id):
            order_id = call.data.split(":")[1]
            order = db_session.query(Order).filter_by(order_id=order_id).first()
            
            if order:
                payment = db_session.query(PaymentTransaction).filter_by(order_id=order.id).first()
                
                order_details = (
                    f"🔍 *Order #{order.order_id} Details*\n\n"
                    f"👤 User: {order.telegram_username}\n"
                    f"📱 Plan: {order.plan_name}\n"
                    f"💰 Amount: ${order.amount}\n"
                    f"📅 Created: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                    f"🔄 Status: {order.status}\n\n"
                )
                
                if payment:
                    order_details += (
                        f"💳 *Payment Information*\n"
                        f"Payment ID: {payment.payment_id}\n"
                        f"Status: {payment.status}\n"
                    )
                
                markup = types.InlineKeyboardMarkup(row_width=2)
                approve_button = types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_order:{order.order_id}")
                reject_button = types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_order:{order.order_id}")
                back_button = types.InlineKeyboardButton("🔙 Back to Orders", callback_data="admin_orders")
                
                markup.add(approve_button, reject_button)
                markup.add(back_button)
                
                bot.edit_message_text(
                    order_details,
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
    
    elif call.data.startswith("approve_order:"):
        user_id = call.from_user.id
        
        if is_admin(user_id):
            order_id = call.data.split(":")[1]
            order = db_session.query(Order).filter_by(order_id=order_id).first()
            
            if order:
                # Ask for activation link
                activation_request = (
                    f"Please enter the activation link for order #{order.order_id}:\n\n"
                    f"This will be sent to the user {order.telegram_username}"
                )
                
                sent_msg = bot.edit_message_text(
                    activation_request,
                    call.message.chat.id,
                    call.message.message_id
                )
                
                # Register the next step handler
                bot.register_next_step_handler(sent_msg, process_activation_link, order_id=order.order_id)
    
    elif call.data.startswith("reject_order:"):
        user_id = call.from_user.id
        
        if is_admin(user_id):
            order_id = call.data.split(":")[1]
            order = db_session.query(Order).filter_by(order_id=order_id).first()
            
            if order:
                # Ask for rejection reason
                reason_request = (
                    f"Please enter the reason for rejecting order #{order.order_id}:\n\n"
                    f"This will be sent to the user {order.telegram_username}"
                )
                
                sent_msg = bot.edit_message_text(
                    reason_request,
                    call.message.chat.id,
                    call.message.message_id
                )
                
                # Register the next step handler
                bot.register_next_step_handler(sent_msg, process_rejection_reason, order_id=order.order_id)
    
    elif call.data == "back_to_admin":
        bot.edit_message_text(
            "👨‍💼 *Admin Panel*\n\nWelcome to the admin panel. Please select an option below:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=create_admin_menu()
        )
    
    elif call.data == "admin_plans":
        user_id = call.from_user.id
        
        if is_admin(user_id):
            plans = config_manager.get_subscription_plans()
            
            plans_text = "🏷️ *Subscription Plans*\n\n"
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            
            for plan in plans:
                plans_text += f"📌 {plan['name']}\n"
                plans_text += f"💰 Price: ${plan['price']}\n"
                plans_text += f"📝 Description: {plan['description']}\n\n"
                
                edit_button = types.InlineKeyboardButton(
                    f"Edit {plan['name']}",
                    callback_data=f"edit_plan:{plan['id']}"
                )
                markup.add(edit_button)
            
            add_button = types.InlineKeyboardButton("➕ Add New Plan", callback_data="add_plan")
            back_button = types.InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="back_to_admin")
            
            markup.add(add_button)
            markup.add(back_button)
            
            bot.edit_message_text(
                plans_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=markup
            )
    
    elif call.data == "payment_confirmed":
        user = get_or_create_user(call.message)
        
        # Find the latest pending order for this user
        order = db_session.query(Order).filter_by(
            user_id=user.id,
            status="AWAITING_PAYMENT"
        ).order_by(Order.created_at.desc()).first()
        
        if order:
            # Update order status
            order.status = "ADMIN_REVIEW"
            order.updated_at = datetime.utcnow()
            db_session.commit()
            
            confirmation_text = (
                "✅ Thank you for your confirmation!\n\n"
                "⏳ Your order has been sent for review by our support team.\n"
                f"After payment verification, Premium will be activated for {order.telegram_username}.\n\n"
                f"🔍 Order #: {order.order_id}\n\n"
                "⌛️ This process usually takes 1-24 hours. Please be patient."
            )
            
            bot.edit_message_text(
                confirmation_text,
                call.message.chat.id,
                call.message.message_id
            )
            
            # Notify admins about new order for review
            notify_admins_about_order(order)
        else:
            bot.answer_callback_query(call.id, "No pending order found.", show_alert=True)

# Message handlers for multi-step processes
def process_username_step(message, plan_id):
    user = get_or_create_user(message)
    plan = config_manager.get_plan_by_id(plan_id)
    
    if not plan:
        bot.send_message(message.chat.id, "❌ Error: Plan not found. Please try again.")
        return
    
    username = message.text.strip()
    
    # Simple validation
    if not username.startswith('@'):
        bot.send_message(
            message.chat.id,
            "❌ Invalid username format. Username must start with @. Please try again."
        )
        # Re-register the handler
        bot.register_next_step_handler(message, process_username_step, plan_id=plan_id)
        return
    
    # Create a new order
    order_id = generate_order_id()
    expires_at = datetime.utcnow() + timedelta(hours=ORDER_EXPIRATION_HOURS)
    
    new_order = Order(
        order_id=order_id,
        user_id=user.id,
        plan_id=plan_id,
        plan_name=plan['name'],
        amount=plan['price'],
        currency='USD',
        status='PENDING',
        telegram_username=username,
        created_at=datetime.utcnow(),
        expires_at=expires_at
    )
    
    db_session.add(new_order)
    db_session.commit()
    
    # Create payment with NowPayments
    try:
        payment_response = nowpayments_api.create_payment(
            price=plan['price'],
            currency='USD',
            pay_currency='TRX',
            order_id=order_id,
            order_description=f"Telegram Premium: {plan['name']} for {username}"
        )
        
        if payment_response and 'payment_id' in payment_response:
            # Save payment information
            payment = PaymentTransaction(
                payment_id=payment_response['payment_id'],
                order_id=new_order.id,
                amount=plan['price'],
                currency='USD',
                pay_currency='TRX',
                status='WAITING',
                created_at=datetime.utcnow()
            )
            
            db_session.add(payment)
            
            # Update order with payment information
            new_order.payment_id = payment_response['payment_id']
            new_order.payment_url = payment_response.get('pay_address', '')
            new_order.status = 'AWAITING_PAYMENT'
            
            db_session.commit()
            
            # Send payment instructions
            payment_instructions = (
                f"✅ Your order has been created successfully!\n\n"
                f"📝 *Order Details:*\n"
                f"◾️ Plan: {plan['name']}\n"
                f"◾️ Price: ${plan['price']}\n"
                f"◾️ Username: {username}\n"
                f"◾️ Order #: {order_id}\n\n"
                f"💳 Please send *{payment_response.get('pay_amount', plan['price'])} {payment_response.get('pay_currency', 'TRX')}* to the following address:\n\n"
                f"`{payment_response.get('pay_address', '')}`\n\n"
                f"⏳ This order will expire in {ORDER_EXPIRATION_HOURS} hours.\n\n"
                f"🔍 After making the payment, click the 'Payment Confirmed' button below."
            )
            
            markup = types.InlineKeyboardMarkup()
            confirm_button = types.InlineKeyboardButton("💰 Payment Confirmed", callback_data="payment_confirmed")
            markup.add(confirm_button)
            
            bot.send_message(
                message.chat.id,
                payment_instructions,
                parse_mode="Markdown",
                reply_markup=markup
            )
        else:
            # Handle payment creation error
            bot.send_message(
                message.chat.id,
                "❌ Error creating payment. Please try again later or contact support."
            )
            
            # Delete the order
            db_session.delete(new_order)
            db_session.commit()
    except Exception as e:
        logger.error(f"Error creating payment: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Error creating payment. Please try again later or contact support."
        )
        
        # Delete the order
        db_session.delete(new_order)
        db_session.commit()

def process_activation_link(message, order_id):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        activation_link = message.text.strip()
        
        order = db_session.query(Order).filter_by(order_id=order_id).first()
        
        if order:
            # Update order status and activation link
            order.status = 'APPROVED'
            order.activation_link = activation_link
            order.updated_at = datetime.utcnow()
            db_session.commit()
            
            # Notify user about approved order
            try:
                customer = db_session.query(User).get(order.user_id)
                
                if customer:
                    approval_message = (
                        f"🎉 Congratulations! Your order has been approved!\n\n"
                        f"✅ Telegram Premium has been activated for {order.telegram_username}.\n\n"
                        f"📝 *Order Details:*\n"
                        f"◾️ Plan: {order.plan_name}\n"
                        f"◾️ Price: ${order.amount}\n"
                        f"◾️ Order #: {order.order_id}\n"
                        f"◾️ Activation Date: {datetime.utcnow().strftime('%Y-%m-%d')}\n\n"
                        f"🔗 *Activation Link:* {activation_link}\n\n"
                        f"❓ If you have any questions or issues, contact our support (/support)."
                    )
                    
                    bot.send_message(
                        customer.telegram_id,
                        approval_message,
                        parse_mode="Markdown"
                    )
            except Exception as e:
                logger.error(f"Error notifying user about approved order: {e}")
            
            # Confirmation for admin
            admin_confirmation = (
                f"✅ Order #{order_id} has been approved successfully.\n\n"
                f"Activation link sent to user: {activation_link}"
            )
            
            markup = types.InlineKeyboardMarkup()
            back_button = types.InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="back_to_admin")
            markup.add(back_button)
            
            bot.send_message(
                message.chat.id,
                admin_confirmation,
                reply_markup=markup
            )
        else:
            bot.send_message(message.chat.id, f"❌ Error: Order #{order_id} not found.")
    else:
        bot.send_message(message.chat.id, "⛔ You don't have permission to perform this action.")

def process_rejection_reason(message, order_id):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        rejection_reason = message.text.strip()
        
        order = db_session.query(Order).filter_by(order_id=order_id).first()
        
        if order:
            # Update order status and admin notes
            order.status = 'REJECTED'
            order.admin_notes = rejection_reason
            order.updated_at = datetime.utcnow()
            db_session.commit()
            
            # Notify user about rejected order
            try:
                customer = db_session.query(User).get(order.user_id)
                
                if customer:
                    rejection_message = (
                        f"❌ Unfortunately, your order has been rejected.\n\n"
                        f"📝 *Order Details:*\n"
                        f"◾️ Plan: {order.plan_name}\n"
                        f"◾️ Price: ${order.amount}\n"
                        f"◾️ Order #: {order.order_id}\n\n"
                        f"📌 Reason: {rejection_reason}\n\n"
                        f"❓ For more information or assistance, contact our support (/support)."
                    )
                    
                    bot.send_message(
                        customer.telegram_id,
                        rejection_message,
                        parse_mode="Markdown"
                    )
            except Exception as e:
                logger.error(f"Error notifying user about rejected order: {e}")
            
            # Confirmation for admin
            admin_confirmation = (
                f"❌ Order #{order_id} has been rejected.\n\n"
                f"Reason: {rejection_reason}"
            )
            
            markup = types.InlineKeyboardMarkup()
            back_button = types.InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="back_to_admin")
            markup.add(back_button)
            
            bot.send_message(
                message.chat.id,
                admin_confirmation,
                reply_markup=markup
            )
        else:
            bot.send_message(message.chat.id, f"❌ Error: Order #{order_id} not found.")
    else:
        bot.send_message(message.chat.id, "⛔ You don't have permission to perform this action.")

# Utility functions
def notify_admins_about_order(order):
    """Notify all admins about a new order for review"""
    admin_ids = config_manager.get_bot_admins()
    
    if not admin_ids:
        logger.warning("No admin IDs configured for notifications")
        return
    
    notification = (
        f"🔔 *New Order Requires Review*\n\n"
        f"Order #: {order.order_id}\n"
        f"Plan: {order.plan_name}\n"
        f"Username: {order.telegram_username}\n"
        f"Amount: ${order.amount}\n"
        f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"Please review this order in the admin panel."
    )
    
    for admin_id in admin_ids:
        try:
            bot.send_message(admin_id, notification, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error sending notification to admin {admin_id}: {e}")

# Polling mode for development
def start_polling():
    """Start the bot in polling mode"""
    logger.info("Starting bot in polling mode")
    try:
        # First, remove any existing webhook
        bot.remove_webhook()
        logger.info("Webhook removed, starting polling")
        
        # Log bot information
        bot_info = bot.get_me()
        logger.info(f"Bot started: @{bot_info.username} (ID: {bot_info.id})")
        
        # Start polling with better error handling
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.error(f"Error starting polling: {str(e)}")
        logger.exception(e)
        
# For webhook mode in production
def set_webhook(webhook_url):
    """Set webhook for the bot"""
    logger.info(f"Setting webhook to: {webhook_url}")
    try:
        # First, remove any existing webhook
        bot.remove_webhook()
        logger.info("Existing webhook removed")
        
        # Set the new webhook
        result = bot.set_webhook(url=webhook_url)
        
        if result:
            # Get webhook info to verify
            webhook_info = bot.get_webhook_info()
            logger.info(f"Webhook set successfully. Info: {webhook_info}")
            return True
        else:
            logger.error("Failed to set webhook")
            return False
    except Exception as e:
        logger.error(f"Error setting webhook: {str(e)}")
        logger.exception(e)
        return False

# Function to process webhook updates from Flask
def process_webhook_update(update_json):
    """Process webhook update from Flask"""
    logger.info(f"Received webhook update")
    try:
        update = telebot.types.Update.de_json(update_json)
        bot.process_new_updates([update])
        return True
    except Exception as e:
        logger.error(f"Error processing webhook update: {str(e)}")
        logger.exception(e)
        return False

if __name__ == "__main__":
    logger.info("Bot script started directly")
    
    # Check if bot is enabled in config
    if config_manager.get_config_value("bot_enabled", default=False):
        logger.info("Bot is enabled, starting in polling mode")
        start_polling()
    else:
        logger.warning("Bot is disabled in configuration. Enable it from admin panel.")
