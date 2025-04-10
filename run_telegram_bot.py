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

# Initialize NowPayments API client using key from config or environment
NOWPAYMENTS_API_KEY = config_manager.get_config_value("nowpayments_api_key") or os.environ.get("NOWPAYMENTS_API_KEY")
logger.info("Initializing NowPayments API client")
nowpayments_api = NowPayments(NOWPAYMENTS_API_KEY)
if not NOWPAYMENTS_API_KEY:
    logger.warning("No NowPayments API key provided. Payment functionality will not work.")

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

def create_subscription_required_message(chat_id, required_channel):
    """
    Creates and sends a message asking the user to subscribe to the required channel.
    Uses English instead of Farsi.
    
    Args:
        chat_id: The user's chat ID
        required_channel: The channel username or ID
    
    Returns:
        None
    """
    # Create "Join Channel" button
    markup = types.InlineKeyboardMarkup(row_width=1)
    channel_name = required_channel
    if not channel_name.startswith('@') and not channel_name.startswith('-100'):
        channel_name = f"@{channel_name}"
        
    join_button = types.InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{channel_name.replace('@', '')}")
    check_button = types.InlineKeyboardButton("✅ Check Subscription", callback_data="check_subscription")
    markup.add(join_button, check_button)
    
    subscription_text = (
        "⚠️ *Required Subscription*\n\n"
        "To use this bot, you must join the following channel:\n"
        f"{channel_name}\n\n"
        "After joining, click the \"Check Subscription\" button below."
    )
    
    bot.send_message(chat_id, subscription_text, parse_mode="Markdown", reply_markup=markup)
    return

def check_channel_subscription(user_id):
    """
    Check if user is subscribed to required channel
    Returns True if:
    - Subscription is not required
    - Required channel is not set
    - User is subscribed to the required channel
    Returns False if user is not subscribed
    """
    # If subscription is not required or channel is not set, return True
    if not config_manager.is_channel_subscription_required():
        return True
        
    required_channel = config_manager.get_required_channel()
    if not required_channel:
        return True
    
    try:
        # Check user's membership in the channel
        chat_member = bot.get_chat_member(required_channel, user_id)
        
        # Check if user is a member, creator, or administrator of the channel
        return chat_member.status in ['member', 'creator', 'administrator']
    except Exception as e:
        logger.error(f"Error checking channel subscription: {str(e)}")
        # If there's an error (e.g., bot is not in the channel), don't block the user
        return True

def create_main_menu():
    """Create the main menu markup"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    plans_button = types.InlineKeyboardButton("📱 Subscription Plans", callback_data="show_plans")
    my_orders_button = types.InlineKeyboardButton("🛒 My Orders", callback_data="my_orders")
    support_button = types.InlineKeyboardButton("🆘 Support", callback_data="support")
    
    markup.add(plans_button, my_orders_button, support_button)
    
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
    channels_button = types.InlineKeyboardButton("📢 Channels", callback_data="admin_channels")
    
    markup.add(orders_button, plans_button)
    markup.add(support_button, admins_button)
    markup.add(channels_button)
    
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
    
    # Check if user needs to subscribe to channel
    if not check_channel_subscription(message.from_user.id):
        required_channel = config_manager.get_required_channel()
        create_subscription_required_message(message.chat.id, required_channel)
        return
    
    # Check if the start command has parameters
    command_parts = message.text.split()
    
    if len(command_parts) > 1:
        # Parse the start parameter
        param = command_parts[1]
        
        if param == 'premium':
            # User clicked "Get Premium" button
            return handle_plans(message)
        
        elif param == 'prices':
            # User clicked "Prices and Plans" button
            return handle_plans(message)
        
        elif param == 'features':
            # User clicked "Features" button
            features_text = (
                "✨ *Telegram Premium Features* ✨\n\n"
                "💎 *Exclusive Access:*\n"
                "• Custom stickers and reactions\n"
                "• Premium badges and app icons\n"
                "• Animated profile pictures\n\n"
                
                "🚀 *Enhanced Capabilities:*\n"
                "• 4GB file uploads (instead of 2GB)\n"
                "• Faster download speeds\n"
                "• Voice-to-text conversion\n"
                "• No ads in public channels\n\n"
                
                "📊 *Expanded Limits:*\n"
                "• Join up to 1000 channels and groups\n"
                "• Follow up to 1000 public channels\n"
                "• Pin up to 10 chats in your main list\n"
                "• Save up to 10 favorite stickers\n\n"
                
                "🔍 To purchase Premium, tap 'Plans' below 👇"
            )
            
            markup = types.InlineKeyboardMarkup()
            plans_button = types.InlineKeyboardButton("📱 View Plans", callback_data="show_plans")
            markup.add(plans_button)
            
            bot.send_message(message.chat.id, features_text, parse_mode="Markdown", reply_markup=markup)
            return
        
        elif param == 'support':
            # User clicked "Support" button
            return handle_support(message)
        
        elif param.startswith('order_'):
            # Admin clicked "View Order" from notification
            order_id = param[6:]  # Extract order ID part
            if is_admin(message.from_user.id):
                # Here we would show order details to admin
                bot.send_message(message.chat.id, f"Loading order #{order_id} details...")
                # Show dummy admin actions for now
                markup = types.InlineKeyboardMarkup()
                approve_button = types.InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve:{order_id}")
                reject_button = types.InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject:{order_id}")
                markup.row(approve_button, reject_button)
                bot.send_message(message.chat.id, f"Order #{order_id} loaded.", reply_markup=markup)
            else:
                bot.send_message(message.chat.id, "⛔ You don't have permission to view this order.")
            return
    
    # Default welcome message
    welcome_text = (
        f"Hello, {message.from_user.first_name}! 👋\n\n"
        "Welcome to the Telegram Premium Subscription Bot.\n"
        "You can purchase Telegram Premium subscriptions using cryptocurrency.\n\n"
        "Please select an option from the menu below:"
    )
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_menu())

@bot.message_handler(commands=['plans'])
def handle_plans(message):
    # Check if user needs to subscribe to channel
    if not check_channel_subscription(message.from_user.id):
        required_channel = config_manager.get_required_channel()
        create_subscription_required_message(message.chat.id, required_channel)
        return
    
    plans = config_manager.get_subscription_plans()
    
    # Prepare plans message
    plans_text = "📱 *Available Subscription Plans*\n\n"
    
    for plan in plans:
        plans_text += f"🔹 *{plan['name']}* - ${plan['price']}\n"
        plans_text += f"{plan['description']}\n\n"
    
    plans_text += "Select a plan to proceed with your purchase:"
    
    bot.send_message(message.chat.id, plans_text, parse_mode="Markdown", reply_markup=create_plans_menu())

@bot.message_handler(commands=['orders', 'myorders'])
def handle_my_orders(message):
    # Check if user needs to subscribe to channel
    if not check_channel_subscription(message.from_user.id):
        required_channel = config_manager.get_required_channel()
        create_subscription_required_message(message.chat.id, required_channel)
        return
        
    user = get_or_create_user(message)
    # Get user's orders from the database
    orders = db_session.query(Order).filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
    
    if orders:
        orders_text = "🛒 *Your Orders*\n\n"
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for order in orders:
            # Add emoji for order status
            status_emoji = "⏳"  # Pending by default
            if order.status == "APPROVED":
                status_emoji = "✅"  # Approved
            elif order.status == "REJECTED":
                status_emoji = "❌"  # Rejected
            elif order.status == "PAYMENT_RECEIVED":
                status_emoji = "💰"  # Payment received
            
            # Format order information
            orders_text += f"{status_emoji} *Order #{order.order_id}*\n"
            orders_text += f"📱 Plan: {order.plan_name}\n"
            orders_text += f"💵 Amount: ${order.amount}\n"
            orders_text += f"📅 Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n"
            orders_text += f"🔄 Status: {order.status}\n"
            
            # Add activation link if approved
            if order.status == "APPROVED" and order.activation_link:
                orders_text += f"🔗 [Activation Link]({order.activation_link})\n"
            
            orders_text += "\n"
            
            # Add button to view order details
            view_button = types.InlineKeyboardButton(
                f"View Order #{order.order_id} Details",
                callback_data=f"view_order:{order.order_id}"
            )
            markup.add(view_button)
        
        # Add back button
        back_button = types.InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")
        markup.add(back_button)
        
        bot.send_message(message.chat.id, orders_text, parse_mode="Markdown", reply_markup=markup)
    else:
        # No orders found
        markup = types.InlineKeyboardMarkup()
        plans_button = types.InlineKeyboardButton("📱 Browse Plans", callback_data="show_plans")
        back_button = types.InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")
        markup.add(plans_button)
        markup.add(back_button)
        
        bot.send_message(
            message.chat.id,
            "🛒 *Your Orders*\n\nYou don't have any orders yet. Browse our subscription plans to make a purchase!",
            parse_mode="Markdown",
            reply_markup=markup
        )

@bot.message_handler(commands=['help'])
def handle_help(message):
    help_text = (
        "📚 *Telegram Premium Subscription Bot Help*\n\n"
        "This bot allows you to purchase Telegram Premium subscriptions using cryptocurrency.\n\n"
        "*Available Commands:*\n"
        "/start - Start the bot and see the main menu\n"
        "/plans - View available subscription plans\n"
        "/orders - View your orders\n"
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
    if call.data == "check_subscription":
        # Check if user is subscribed to the required channel
        if check_channel_subscription(call.from_user.id):
            # User is subscribed, show the main menu
            bot.answer_callback_query(call.id, "✅ Subscription confirmed!")
            bot.edit_message_text(
                "Welcome to the Telegram Premium Subscription Bot.\nPlease select an option from the menu below:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=create_main_menu()
            )
        else:
            # User is not subscribed yet
            required_channel = config_manager.get_required_channel()
            channel_name = required_channel
            if not channel_name.startswith('@') and not channel_name.startswith('-100'):
                channel_name = f"@{channel_name}"
                
            bot.answer_callback_query(call.id, "⚠️ You haven't joined the channel yet!", show_alert=True)
            
    elif call.data == "show_plans":
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
    
    # Help feature removed
    # elif call.data == "help":
    #     handle_help(call.message)
        
    elif call.data == "support":
        handle_support(call.message)
        
    elif call.data == "my_orders":
        # When coming from a callback, we need to extract the user ID from the callback
        # Instead of relying on message.from_user which would be the bot 
        user_id = str(call.from_user.id)
        user = db_session.query(User).filter_by(telegram_id=user_id).first()
        
        if not user:
            # If user is not found, create it - though this should be rare in this context
            user = User(
                telegram_id=user_id,
                username=call.from_user.username,
                first_name=call.from_user.first_name,
                last_name=call.from_user.last_name
            )
            db_session.add(user)
            db_session.commit()
            logger.info(f"Created new user from callback: {user.username}")
            
        # Get user's orders from the database
        orders = db_session.query(Order).filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
        
        if orders:
            orders_text = "🛒 *Your Orders*\n\n"
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            
            for order in orders:
                # Add emoji for order status
                status_emoji = "⏳"  # Pending by default
                if order.status == "APPROVED":
                    status_emoji = "✅"  # Approved
                elif order.status == "REJECTED":
                    status_emoji = "❌"  # Rejected
                elif order.status == "PAYMENT_RECEIVED":
                    status_emoji = "💰"  # Payment received
                elif order.status == "ADMIN_REVIEW":
                    status_emoji = "👨‍💼"  # Admin review
                elif order.status == "AWAITING_PAYMENT":
                    status_emoji = "💸"  # Awaiting payment
                
                # Format order information
                orders_text += f"{status_emoji} *Order #{order.order_id}*\n"
                orders_text += f"📱 Plan: {order.plan_name}\n"
                orders_text += f"💵 Amount: ${order.amount}\n"
                orders_text += f"📅 Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                orders_text += f"🔄 Status: {order.status}\n"
                
                # Add activation link if approved
                if order.status == "APPROVED" and order.activation_link:
                    orders_text += f"🔗 [Activation Link]({order.activation_link})\n"
                
                orders_text += "\n"
                
                # Add button to view order details
                view_button = types.InlineKeyboardButton(
                    f"View Order #{order.order_id} Details",
                    callback_data=f"view_order:{order.order_id}"
                )
                markup.add(view_button)
            
            # Add back button
            back_button = types.InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")
            markup.add(back_button)
            
            bot.edit_message_text(
                orders_text, 
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown", 
                reply_markup=markup,
                disable_web_page_preview=False  # Allow preview for activation links
            )
        else:
            # No orders found
            markup = types.InlineKeyboardMarkup()
            plans_button = types.InlineKeyboardButton("📱 Browse Plans", callback_data="show_plans")
            back_button = types.InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")
            markup.add(plans_button)
            markup.add(back_button)
            
            bot.edit_message_text(
                "🛒 *Your Orders*\n\nYou don't have any orders yet. Browse our subscription plans to make a purchase!",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=markup
            )
        
    elif call.data.startswith("view_order:"):
        order_id = call.data.split(":")[1]
        # Get the user from the callback
        user_id = str(call.from_user.id)
        user = db_session.query(User).filter_by(telegram_id=user_id).first()
        # Get the order
        order = db_session.query(Order).filter_by(order_id=order_id, user_id=user.id).first()
        
        if order:
            # Get payment info
            payment = db_session.query(PaymentTransaction).filter_by(order_id=order.id).first()
            
            # Prepare order details message
            order_details = (
                f"🔍 *Order #{order.order_id} Details*\n\n"
                f"📱 Plan: {order.plan_name}\n"
                f"💰 Amount: ${order.amount}\n"
                f"👤 Username: {order.telegram_username}\n"
                f"📅 Created: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                f"🔄 Status: {order.status}\n"
            )
            
            # Add expiration date if available
            if order.expires_at:
                order_details += f"⏱️ Expires: {order.expires_at.strftime('%Y-%m-%d %H:%M')}\n"
            
            # Add activation link if approved
            if order.status == "APPROVED" and order.activation_link:
                order_details += f"\n🔗 [Activation Link]({order.activation_link})\n"
            
            # Add admin notes if available
            if order.admin_notes:
                order_details += f"\n📝 *Notes:*\n{order.admin_notes}\n"
            
            # Add payment details if available
            if payment:
                order_details += (
                    f"\n💳 *Payment Information*\n"
                    f"ID: {payment.payment_id}\n"
                    f"Status: {payment.status}\n"
                    f"Currency: {payment.pay_currency}\n"
                )
                
                if payment.completed_at:
                    order_details += f"Completed: {payment.completed_at.strftime('%Y-%m-%d %H:%M')}\n"
            
            # Create back button
            markup = types.InlineKeyboardMarkup()
            back_button = types.InlineKeyboardButton("🔙 Back to My Orders", callback_data="my_orders")
            markup.add(back_button)
            
            bot.edit_message_text(
                order_details,
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=markup,
                disable_web_page_preview=False  # Allow preview for activation link
            )
    
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
                
                # Check if this is from a channel message
                if hasattr(call.message, 'sender_chat') and call.message.sender_chat and call.message.sender_chat.type == 'channel':
                    # For channel messages, we just acknowledge and open in private chat
                    bot.answer_callback_query(call.id, "🔍 Opening order details in private chat...")
                    
                    # Create buttons for private chat
                    markup = types.InlineKeyboardMarkup(row_width=2)
                    approve_button = types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_order:{order.order_id}")
                    reject_button = types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_order:{order.order_id}")
                    markup.add(approve_button, reject_button)
                    
                    # Send to admin's private chat
                    bot.send_message(
                        user_id,  # Send to admin's private chat
                        order_details,
                        parse_mode="Markdown",
                        reply_markup=markup
                    )
                else:
                    # Regular private chat handling
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
                # Check if this is a callback from a channel
                if hasattr(call.message, 'sender_chat') and call.message.sender_chat and call.message.sender_chat.type == 'channel':
                    # When in a channel, we can't edit message and use next_step_handler
                    # So we send a direct message to the admin instead
                    bot.answer_callback_query(call.id, "✅ Opening order approval in private chat...")
                    
                    # Send a new message to the admin's private chat
                    activation_request = (
                        f"✅ *Order Approval - #{order.order_id}*\n\n"
                        f"Please enter the activation link for order #{order.order_id}:\n\n"
                        f"This will be sent to {order.telegram_username}\n\n"
                        f"*Reply to this message with the activation link*"
                    )
                    
                    # We need to send a new message to the admin's private chat
                    sent_msg = bot.send_message(
                        user_id,  # Send to admin's private chat
                        activation_request,
                        parse_mode="Markdown"
                    )
                    
                    # Register the next step handler for the private message
                    bot.register_next_step_handler(sent_msg, process_activation_link, order_id=order.order_id)
                else:
                    # Regular private chat flow
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
                # Check if this is a callback from a channel
                if hasattr(call.message, 'sender_chat') and call.message.sender_chat and call.message.sender_chat.type == 'channel':
                    # When in a channel, we can't edit message and use next_step_handler
                    # So we send a direct message to the admin instead
                    bot.answer_callback_query(call.id, "❌ Opening order rejection in private chat...")
                    
                    # Send a new message to the admin's private chat
                    rejection_request = (
                        f"❌ *Order Rejection - #{order.order_id}*\n\n"
                        f"Please enter the reason for rejecting order #{order.order_id}:\n\n"
                        f"This will be sent to {order.telegram_username}\n\n"
                        f"*Reply to this message with the rejection reason*"
                    )
                    
                    # We need to send a new message to the admin's private chat
                    sent_msg = bot.send_message(
                        user_id,  # Send to admin's private chat
                        rejection_request,
                        parse_mode="Markdown"
                    )
                    
                    # Register the next step handler for the private message
                    bot.register_next_step_handler(sent_msg, process_rejection_reason, order_id=order.order_id)
                else:
                    # Regular private chat flow
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
    
    elif call.data == "admin_channels":
        user_id = call.from_user.id
        
        if is_admin(user_id):
            # Get current channel settings
            admin_channel = config_manager.get_admin_channel()
            public_channel = config_manager.get_public_channel()
            required_channel = config_manager.get_required_channel()
            notification_enabled = config_manager.get_config_value('notification_enabled', False)
            channel_subscription_required = config_manager.is_channel_subscription_required()
            
            channels_text = (
                "📢 *Channel Settings*\n\n"
                f"*Admin Channel:* {admin_channel or 'Not set'}\n"
                f"*Public Channel:* {public_channel or 'Not set'}\n"
                f"*Required Channel:* {required_channel or 'Not set'}\n"
                f"*Channel Subscription Required:* {'Enabled' if channel_subscription_required else 'Disabled'}\n"
                f"*Public Notifications:* {'Enabled' if notification_enabled else 'Disabled'}\n\n"
                "Please provide channel information using the format below:\n"
                "```\n"
                "admin: @channel_name or -100123456789\n"
                "public: @channel_name or -100123456789\n"
                "required: @channel_name or -100123456789\n"
                "required_subscription: on/off\n"
                "notifications: on/off\n"
                "```\n\n"
                "Please ensure that the bot has been added as an admin to the channels."
            )
            
            markup = types.InlineKeyboardMarkup()
            back_button = types.InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="back_to_admin")
            markup.add(back_button)
            
            sent_msg = bot.edit_message_text(
                channels_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=markup
            )
            
            # Register the next step handler for channel settings
            bot.register_next_step_handler(sent_msg, process_channel_settings)
    
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
    
    elif call.data.startswith("payment_confirmed:"):
        user = get_or_create_user(call.message)
        
        # Extract order ID from callback data
        order_id = call.data.split(':')[1]
        logger.info(f"Payment confirmation received for order #{order_id}")
        
        # Find the specific order
        order = db_session.query(Order).filter_by(
            order_id=order_id,
            status="AWAITING_PAYMENT"
        ).first()
        
        if not order:
            # Try to find by user as fallback
            logger.warning(f"Order #{order_id} not found, trying to find by user")
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
            
            # Add navigation buttons after payment confirmation
            markup = types.InlineKeyboardMarkup()
            view_orders_button = types.InlineKeyboardButton("🛒 My Orders", callback_data="my_orders")
            plans_button = types.InlineKeyboardButton("📱 Browse Plans", callback_data="show_plans")
            main_menu_button = types.InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main")
            markup.add(view_orders_button)
            markup.add(plans_button)
            markup.add(main_menu_button)
            
            bot.edit_message_text(
                confirmation_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            
            # Notify admins about new order for review
            notify_admins_about_order(order)
        else:
            bot.answer_callback_query(call.id, "No pending order found.", show_alert=True)
            
    elif call.data == "payment_help":
        # Provide help with payment
        payment_help_text = (
            "💳 *How to pay with TRX (Tron)*\n\n"
            "1️⃣ *Get TRX*: Purchase TRX from a cryptocurrency exchange like Binance, Coinbase, or similar platforms.\n\n"
            "2️⃣ *Send Payment*: Transfer the exact amount of TRX to the wallet address provided in your order.\n\n"
            "3️⃣ *Confirm Payment*: After sending the payment, click the 'Payment Confirmed' button in your order message.\n\n"
            "⚠️ *Important Notes*:\n"
            "- Send exactly the requested amount\n"
            "- Make sure to use the Tron (TRX) network for your transaction\n"
            "- Transaction confirmations may take 10-30 minutes\n\n"
            "🆘 If you need further assistance, contact our support (/support)"
        )
        
        # Create buttons for the help message
        markup = types.InlineKeyboardMarkup()
        back_button = types.InlineKeyboardButton("🔙 Back", callback_data="back_to_main")
        support_button = types.InlineKeyboardButton("🆘 Contact Support", callback_data="support")
        markup.add(back_button, support_button)
        
        bot.send_message(
            call.message.chat.id,
            payment_help_text,
            parse_mode="Markdown",
            reply_markup=markup
        )

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
        # Check if NowPayments API key is set
        if not NOWPAYMENTS_API_KEY:
            logger.error("Cannot create payment: NowPayments API key is not set")
            
            # Update the order status to manual review
            new_order.status = 'ADMIN_REVIEW'
            db_session.commit()
            
            # Notify user and admin
            bot.send_message(
                message.chat.id,
                "✅ Your order has been created and will be reviewed by our team.\n\n"
                f"📝 *Order Details:*\n"
                f"◾️ Plan: {plan['name']}\n"
                f"◾️ Price: ${plan['price']}\n"
                f"◾️ Username: {username}\n"
                f"◾️ Order #: {order_id}\n\n"
                "We'll contact you with payment instructions soon.",
                parse_mode="Markdown"
            )
            
            # Notify admins about the new order
            notify_admins_about_order(new_order)
            return
        
        logger.info(f"Creating payment for order #{order_id} - {plan['name']} - ${plan['price']}")
        payment_response = nowpayments_api.create_payment(
            price=plan['price'],
            currency='USD',
            pay_currency='TRX',
            order_id=order_id,
            order_description=f"Telegram Premium: {plan['name']} for {username}"
        )
        
        if payment_response and 'payment_id' in payment_response:
            logger.info(f"Payment created successfully: ID {payment_response['payment_id']}")
            
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
            confirm_button = types.InlineKeyboardButton("💰 Payment Confirmed", callback_data=f"payment_confirmed:{order_id}")
            help_button = types.InlineKeyboardButton("🆘 Help with Payment", callback_data="payment_help")
            plans_button = types.InlineKeyboardButton("📱 Browse Plans", callback_data="show_plans")
            main_button = types.InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main")
            markup.add(confirm_button)
            markup.add(help_button)
            markup.add(plans_button)
            markup.add(main_button)
            
            bot.send_message(
                message.chat.id,
                payment_instructions,
                parse_mode="Markdown",
                reply_markup=markup
            )
        else:
            # Handle payment creation error - switch to manual mode
            logger.warning(f"Payment response error: {payment_response}")
            
            # Update the order status to admin review
            new_order.status = 'ADMIN_REVIEW'
            db_session.commit()
            
            # Notify admins about the new order
            notify_admins_about_order(new_order)
            
            # Notify user with buttons
            markup = types.InlineKeyboardMarkup()
            plans_button = types.InlineKeyboardButton("📱 Browse Plans", callback_data="show_plans")
            orders_button = types.InlineKeyboardButton("🛒 My Orders", callback_data="my_orders")
            main_button = types.InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main")
            markup.add(orders_button)
            markup.add(plans_button)
            markup.add(main_button)
            
            bot.send_message(
                message.chat.id,
                "⚠️ Automatic payment creation is currently unavailable.\n\n"
                f"Your order #{order_id} has been created and will be processed manually by our team.\n"
                "We'll contact you shortly with payment instructions.",
                parse_mode="Markdown",
                reply_markup=markup
            )
    except Exception as e:
        logger.error(f"Error creating payment: {e}")
        logger.exception(e)
        
        # Don't delete the order, but change status for admin review
        if new_order:
            try:
                new_order.status = 'ADMIN_REVIEW'
                new_order.admin_notes = f"Payment creation error: {str(e)}"
                db_session.commit()
                
                # Notify admins about the problematic order
                notify_admins_about_order(new_order)
                
                # Notify user with navigation buttons
                markup = types.InlineKeyboardMarkup()
                plans_button = types.InlineKeyboardButton("📱 Browse Plans", callback_data="show_plans")
                orders_button = types.InlineKeyboardButton("🛒 My Orders", callback_data="my_orders")
                main_button = types.InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main")
                markup.add(orders_button)
                markup.add(plans_button)
                markup.add(main_button)
                
                bot.send_message(
                    message.chat.id,
                    "⚠️ We encountered an issue with the payment processor.\n\n"
                    f"Your order #{order_id} has been created and will be processed manually by our team.\n"
                    "We'll contact you shortly with payment instructions.",
                    parse_mode="Markdown",
                    reply_markup=markup
                )
            except Exception as inner_e:
                logger.error(f"Error updating order after payment failure: {inner_e}")
                db_session.rollback()
                
                # Last resort - simple error message
                bot.send_message(
                    message.chat.id,
                    "❌ Error creating payment. Please try again later or contact support."
                )
        else:
            bot.send_message(
                message.chat.id,
                "❌ Error creating payment. Please try again later or contact support."
            )

def process_channel_settings(message):
    """Process channel settings message from admin"""
    user_id = message.from_user.id
    
    if is_admin(user_id):
        try:
            # Parse the text message to extract channel settings
            lines = message.text.strip().split('\n')
            admin_channel = None
            public_channel = None
            required_channel = None
            notification_enabled = None
            channel_subscription_required = None
            
            for line in lines:
                line = line.strip().lower()
                
                if line.startswith('admin:'):
                    admin_channel = line.split(':', 1)[1].strip()
                elif line.startswith('public:'):
                    public_channel = line.split(':', 1)[1].strip()
                elif line.startswith('required:'):
                    required_channel = line.split(':', 1)[1].strip()
                elif line.startswith('required_subscription:'):
                    value = line.split(':', 1)[1].strip()
                    channel_subscription_required = value.lower() in ('on', 'yes', 'true', '1', 'enabled')
                elif line.startswith('notifications:'):
                    value = line.split(':', 1)[1].strip()
                    notification_enabled = value.lower() in ('on', 'yes', 'true', '1', 'enabled')
            
            # Save the settings
            if admin_channel is not None:
                config_manager.set_admin_channel(admin_channel)
            if public_channel is not None:
                config_manager.set_public_channel(public_channel)
            if required_channel is not None:
                config_manager.set_required_channel(required_channel)
            if channel_subscription_required is not None:
                config_manager.set_channel_subscription_required(channel_subscription_required)
            if notification_enabled is not None:
                config_manager.set_config_value('notification_enabled', notification_enabled)
            
            # Send confirmation
            confirmation = (
                "✅ Channel settings updated successfully:\n\n"
                f"Admin Channel: {admin_channel or 'Not set'}\n"
                f"Public Channel: {public_channel or 'Not set'}\n"
                f"Required Channel: {required_channel or 'Not set'}\n"
                f"Channel Subscription Required: {'Enabled' if channel_subscription_required else 'Disabled'}\n"
                f"Public Notifications: {'Enabled' if notification_enabled else 'Disabled'}"
            )
            
            markup = types.InlineKeyboardMarkup()
            back_button = types.InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="back_to_admin")
            markup.add(back_button)
            
            bot.send_message(
                message.chat.id,
                confirmation,
                reply_markup=markup
            )
            
            logger.info(f"Channel settings updated by admin {user_id}")
            logger.info(f"New settings - Admin: {admin_channel}, Public: {public_channel}, Required: {required_channel}, Subscription Required: {channel_subscription_required}, Notifications: {notification_enabled}")
            
        except Exception as e:
            logger.error(f"Error processing channel settings: {e}")
            
            # Send error message
            error_message = (
                "❌ Error updating channel settings. Please use the correct format:\n\n"
                "```\n"
                "admin: @channel_name or -100123456789\n"
                "public: @channel_name or -100123456789\n"
                "required: @channel_name or -100123456789\n"
                "required_subscription: on/off\n"
                "notifications: on/off\n"
                "```"
            )
            
            markup = types.InlineKeyboardMarkup()
            back_button = types.InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="back_to_admin")
            retry_button = types.InlineKeyboardButton("🔄 Try Again", callback_data="admin_channels")
            markup.add(retry_button)
            markup.add(back_button)
            
            bot.send_message(
                message.chat.id,
                error_message,
                parse_mode="Markdown",
                reply_markup=markup
            )
    else:
        bot.send_message(message.chat.id, "⛔ You don't have permission to perform this action.")

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
            
            # Notify user about rejected order using the enhanced notification
            notify_customer_about_rejection(order)
            
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
    admin_channel = config_manager.get_admin_channel()
    public_channel = config_manager.get_public_channel()
    
    # First try to send to admin channel if configured
    if admin_channel:
        try:
            # Create HTML formatted notification
            notification = (
                f"🔔 <b>New Order Requires Review</b>\n\n"
                f"Order #: {order.order_id}\n"
                f"Plan: {order.plan_name}\n"
                f"Username: {order.telegram_username}\n"
                f"Amount: ${order.amount}\n"
                f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"Status: <b>{order.status}</b>\n\n"
                f"⚡️ Please review this order in the admin panel."
            )
            
            # Create admin actions keyboard - using standard callback patterns that match the existing handlers
            markup = types.InlineKeyboardMarkup()
            approve_button = types.InlineKeyboardButton("✅ Activate Premium", callback_data=f"approve_order:{order.order_id}")
            reject_button = types.InlineKeyboardButton("❌ Reject Order", callback_data=f"reject_order:{order.order_id}")
            view_button = types.InlineKeyboardButton("🔍 View Details", callback_data=f"review_order:{order.order_id}")
            markup.row(approve_button, reject_button)
            markup.add(view_button)
            
            # Send to admin channel using HTML parse mode
            bot.send_message(
                admin_channel, 
                notification, 
                parse_mode="HTML",
                reply_markup=markup
            )
            logger.info(f"Notification sent to admin channel: {admin_channel}")
            
            # Also send a notification to the public channel if configured and enabled
            # We're allowing sending to the same channel with a different message
            if public_channel:
                try:
                    # Different message format for public channel announcements
                    public_notification = (
                        f"🌟 <b>NEW ORDER RECEIVED!</b> 🌟\n\n"
                        f"A customer just ordered: <b>{order.plan_name}</b> ✨\n\n"
                        f"🔥 <b>TELEGRAM PREMIUM BENEFITS:</b>\n"
                        f"✓ Higher upload limits (4GB files)\n"
                        f"✓ Exclusive stickers and reactions\n"
                        f"✓ Ad-free experience\n" 
                        f"✓ Premium profile badge\n"
                        f"✓ Voice-to-text conversion\n"
                        f"✓ And much more...\n\n"
                        f"💯 <b>Don't miss out!</b> Get your Premium today!"
                    )
                    
                    # Check if we're sending to the same channel
                    if public_channel == admin_channel:
                        logger.info(f"Public channel is same as admin channel: {public_channel}")
                    
                    # Create attractive inline keyboard with multiple buttons
                    markup = types.InlineKeyboardMarkup(row_width=2)
                    
                    # Main buttons
                    order_button = types.InlineKeyboardButton("💎 Get Premium Now", url=f"https://t.me/{bot.get_me().username}?start=premium")
                    price_button = types.InlineKeyboardButton("💰 View Plans & Pricing", url=f"https://t.me/{bot.get_me().username}?start=plans")
                    
                    # Information buttons
                    features_button = types.InlineKeyboardButton("✨ Premium Features", url=f"https://t.me/{bot.get_me().username}?start=features")
                    support_button = types.InlineKeyboardButton("🆘 Get Help", url=f"https://t.me/{bot.get_me().username}?start=support")
                    
                    # Add buttons in two rows
                    markup.add(order_button, price_button)
                    markup.add(features_button, support_button)
                    
                    bot.send_message(
                        public_channel, 
                        public_notification, 
                        parse_mode="HTML",
                        reply_markup=markup
                    )
                    logger.info(f"Notification sent to public channel: {public_channel}")
                except Exception as e:
                    logger.error(f"Failed to send notification to public channel {public_channel}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to send notification to admin channel {admin_channel}: {e}")
            # Continue to notify individual admins as fallback
    
    # Fallback: Notify individual admins
    if not admin_ids:
        logger.warning("No admin IDs configured for notifications")
        return
    
    # Simpler notification for individual admins
    notification = (
        f"🔔 <b>New Order Requires Review</b>\n\n"
        f"Order #: {order.order_id}\n"
        f"Plan: {order.plan_name}\n"
        f"Username: {order.telegram_username}\n"
        f"Amount: ${order.amount}\n"
        f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"Please review this order in the admin panel."
    )
    
    for admin_id in admin_ids:
        try:
            bot.send_message(admin_id, notification, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error sending notification to admin {admin_id}: {e}")
            
def notify_admins_about_payment(order, transaction):
    """Notify all admins about a completed payment"""
    admin_ids = config_manager.get_bot_admins()
    admin_channel = config_manager.get_admin_channel()
    
    # Format amount with 2 decimal places
    formatted_amount = "{:.2f}".format(transaction.amount)
    
    # Get crypto amount from IPN data if available
    crypto_amount = "N/A"
    crypto_currency = transaction.pay_currency
    
    if transaction.ipn_data:
        pay_amount = transaction.ipn_data.get('pay_amount')
        if pay_amount:
            crypto_amount = pay_amount
    
    # First try to send to admin channel if configured
    if admin_channel:
        try:
            # Create HTML formatted notification
            notification = (
                f"💰 <b>Payment Received!</b>\n\n"
                f"Order #: {order.order_id}\n"
                f"Plan: {order.plan_name}\n"
                f"Username: {order.telegram_username}\n"
                f"Amount: ${formatted_amount}\n"
                f"Crypto: {crypto_amount} {crypto_currency}\n"
                f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"✅ Payment has been verified automatically.\n"
                f"⚡️ This order is ready for activation."
            )
            
            # Create admin actions keyboard using standard callback patterns with clearer button text
            markup = types.InlineKeyboardMarkup()
            approve_button = types.InlineKeyboardButton("✅ Activate Premium", callback_data=f"approve_order:{order.order_id}")
            review_button = types.InlineKeyboardButton("🔍 Review Details", callback_data=f"review_order:{order.order_id}")
            markup.row(approve_button, review_button)
            
            bot.send_message(
                admin_channel, 
                notification, 
                parse_mode="HTML",
                reply_markup=markup
            )
            logger.info(f"Payment notification sent to admin channel: {admin_channel}")
            
            # Important: Do not return here, we want to continue even if admin channel notification succeeds
        except Exception as e:
            logger.error(f"Failed to send payment notification to admin channel {admin_channel}: {e}")
            # Continue to notify individual admins as fallback
    
    # Fallback: Individual admin notifications if channel fails
    if not admin_ids:
        logger.warning("No admin IDs configured for notifications")
        return
    
    # HTML formatted notification for individual admins
    notification = (
        f"💰 <b>Payment Received!</b>\n\n"
        f"Order #: {order.order_id}\n"
        f"Plan: {order.plan_name}\n"
        f"Username: {order.telegram_username}\n"
        f"Amount: ${formatted_amount}\n"
        f"Crypto: {crypto_amount} {crypto_currency}\n"
        f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"ℹ️ Payment has been verified. This order is ready for processing."
    )
    
    # Create inline keyboard for quick actions using standard callback patterns with clearer button text
    markup = types.InlineKeyboardMarkup()
    approve_button = types.InlineKeyboardButton("✅ Activate Premium", callback_data=f"approve_order:{order.order_id}")
    review_button = types.InlineKeyboardButton("🔍 Review", callback_data=f"review_order:{order.order_id}")
    markup.row(approve_button, review_button)
    
    for admin_id in admin_ids:
        try:
            bot.send_message(
                admin_id, 
                notification, 
                parse_mode="HTML",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Error sending payment notification to admin {admin_id}: {e}")
    
    # Also send to public channel if enabled
    send_public_purchase_announcement(order, transaction)
    
    # Also notify the customer
    notify_customer_about_payment(order, transaction)

def notify_customer_about_payment(order, transaction):
    """Notify customer about their payment confirmation"""
    try:
        customer = db_session.query(User).get(order.user_id)
        if not customer:
            logger.error(f"Customer not found for order {order.order_id}")
            return
            
        # Format amount with 2 decimal places
        formatted_amount = "{:.2f}".format(transaction.amount)
            
        # HTML formatted notification
        customer_notification = (
            f"💰 <b>Payment Received!</b>\n\n"
            f"We've received your payment for order #{order.order_id}.\n\n"
            f"<b>Order Details:</b>\n"
            f"◾️ Plan: {order.plan_name}\n"
            f"◾️ Username: {order.telegram_username}\n"
            f"◾️ Amount: ${formatted_amount}\n\n"
            f"Your order is now being processed. You'll receive another message "
            f"when your Telegram Premium is activated."
        )
        
        # Add navigation buttons
        markup = types.InlineKeyboardMarkup()
        view_order_button = types.InlineKeyboardButton("🔍 View Order Details", callback_data=f"view_order:{order.order_id}")
        my_orders_button = types.InlineKeyboardButton("🛒 My Orders", callback_data="my_orders")
        plans_button = types.InlineKeyboardButton("📱 Browse Plans", callback_data="show_plans")
        main_menu_button = types.InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main")
        markup.add(view_order_button)
        markup.add(my_orders_button)
        markup.add(plans_button)
        markup.add(main_menu_button)
        
        bot.send_message(
            customer.telegram_id,
            customer_notification,
            parse_mode="HTML",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Error notifying customer about payment: {e}")
        
def notify_customer_about_approval(order):
    """Notify customer about their approved order with activation link"""
    try:
        # Find the user
        customer = db_session.query(User).get(order.user_id)
        if not customer:
            logger.error(f"Customer not found for order {order.order_id}")
            return False
            
        # Check if we have activation link
        if not order.activation_link:
            logger.error(f"No activation link available for order {order.order_id}")
            return False
            
        # HTML formatted notification
        customer_notification = (
            f"🎉 <b>Your Premium Subscription is Ready!</b>\n\n"
            f"Your order for <b>{order.plan_name}</b> has been approved and processed.\n\n"
            f"<b>Order Details:</b>\n"
            f"◾️ Order #: {order.order_id}\n"
            f"◾️ Username: {order.telegram_username}\n"
            f"◾️ Status: Approved\n\n"
            f"<b>Your Activation Link:</b>\n"
            f"{order.activation_link}\n\n"
            f"Click the link above to activate your Telegram Premium subscription.\n\n"
            f"Thank you for your purchase! If you have any questions, contact our support."
        )
        
        # Create notification with activation link and navigation buttons
        markup = types.InlineKeyboardMarkup()
        activate_button = types.InlineKeyboardButton("🚀 Activate Premium", url=order.activation_link)
        view_order_button = types.InlineKeyboardButton("🔍 View Order Details", callback_data=f"view_order:{order.order_id}")
        my_orders_button = types.InlineKeyboardButton("🛒 My Orders", callback_data="my_orders")
        plans_button = types.InlineKeyboardButton("📱 Browse Plans", callback_data="show_plans")
        main_button = types.InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main")
        support_button = types.InlineKeyboardButton("🆘 Need Help?", callback_data="support")
        markup.add(activate_button)
        markup.add(view_order_button)
        markup.add(my_orders_button)
        markup.add(plans_button)
        markup.add(main_button)
        markup.add(support_button)
        
        bot.send_message(
            customer.telegram_id,
            customer_notification,
            parse_mode="HTML",
            reply_markup=markup
        )
        logger.info(f"Approval notification sent to user {customer.telegram_id} for order #{order.order_id}")
        
        # Also send to the public channel if configured
        public_channel = config_manager.get_public_channel()
        if public_channel:
            try:
                # For public announcement, we don't include the activation link
                public_message = (
                    f"🎉 <b>NEW PREMIUM ACTIVATION!</b> 🎉\n\n"
                    f"A user just received their <b>{order.plan_name}</b> subscription!\n\n"
                    f"🔥 <b>TELEGRAM PREMIUM GIVES YOU:</b>\n"
                    f"✓ Upload files up to 4GB\n"
                    f"✓ Exclusive stickers and reactions\n"
                    f"✓ Ad-free experience\n" 
                    f"✓ Premium badge\n"
                    f"✓ Voice-to-text conversion\n"
                    f"✓ And much more!\n\n"
                    f"💯 <b>Don't miss out!</b> Get yours today!"
                )
                
                # Create eye-catching inline keyboard
                markup = types.InlineKeyboardMarkup(row_width=2)
                order_button = types.InlineKeyboardButton("💎 Get Premium", url=f"https://t.me/{bot.get_me().username}?start=premium")
                price_button = types.InlineKeyboardButton("💰 View Plans", url=f"https://t.me/{bot.get_me().username}?start=plans")
                markup.add(order_button, price_button)
                
                bot.send_message(
                    public_channel, 
                    public_message, 
                    parse_mode="HTML",
                    reply_markup=markup
                )
                logger.info(f"Activation announcement sent to public channel: {public_channel}")
            except Exception as channel_err:
                logger.error(f"Failed to send public channel announcement: {str(channel_err)}")
        
        return True
    except Exception as e:
        logger.error(f"Failed to notify customer about approval: {str(e)}")
        logger.exception(e)
        return False
        
def notify_customer_about_rejection(order):
    """Notify customer about their rejected order and reason"""
    try:
        # Find the user
        customer = db_session.query(User).get(order.user_id)
        if not customer:
            logger.error(f"Customer not found for order {order.order_id}")
            return False
        
        # Prepare rejection reason
        rejection_reason = order.admin_notes or "No specific reason provided."
        
        # HTML formatted notification
        customer_notification = (
            f"❌ <b>Order Rejected</b>\n\n"
            f"Unfortunately, your order for <b>{order.plan_name}</b> has been rejected.\n\n"
            f"<b>Order Details:</b>\n"
            f"◾️ Order #: {order.order_id}\n"
            f"◾️ Username: {order.telegram_username}\n"
            f"◾️ Amount: ${order.amount}\n"
            f"◾️ Status: Rejected\n\n"
            f"<b>Reason:</b>\n{rejection_reason}\n\n"
            f"If you believe this was a mistake or need further assistance, please contact our support team."
        )
        
        # Create notification with support button, navigation and view orders
        markup = types.InlineKeyboardMarkup()
        try_again_button = types.InlineKeyboardButton("🔄 Try Again", callback_data="show_plans")
        view_order_button = types.InlineKeyboardButton("🔍 View Order Details", callback_data=f"view_order:{order.order_id}")
        my_orders_button = types.InlineKeyboardButton("🛒 My Orders", callback_data="my_orders")
        main_button = types.InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main")
        support_button = types.InlineKeyboardButton("🆘 Contact Support", callback_data="support")
        
        markup.add(try_again_button)
        markup.add(view_order_button)
        markup.add(my_orders_button)
        markup.add(main_button)
        markup.add(support_button)
        
        bot.send_message(
            customer.telegram_id,
            customer_notification,
            parse_mode="HTML",
            reply_markup=markup
        )
        logger.info(f"Rejection notification sent to user {customer.telegram_id} for order #{order.order_id}")
        return True
    except Exception as e:
        logger.error(f"Error notifying customer about rejection: {e}")
        return False

def send_public_purchase_announcement(order, transaction):
    """Send purchase announcement to public channel"""
    public_channel = config_manager.get_public_channel()
    admin_channel = config_manager.get_admin_channel()
    notification_enabled = config_manager.get_config_value("notification_enabled", False)
    
    if not public_channel or not notification_enabled:
        logger.warning("Public channel not configured or notifications disabled")
        return
        
    # Check if we're sending to the same channel
    if public_channel == admin_channel:
        logger.info(f"Public channel is same as admin channel: {public_channel}, still sending announcement")
        
    try:
        # Format amount with 2 decimal places
        formatted_amount = "{:.2f}".format(transaction.amount)
        
        # Hide full username for privacy - show only part
        username = order.telegram_username
        if username and len(username) > 4:
            # Show first 2 characters, hide the rest with asterisks, then show @ if present
            if username.startswith('@'):
                masked_username = f"@{username[1:3]}{'*' * (len(username) - 3)}"
            else:
                masked_username = f"{username[0:2]}{'*' * (len(username) - 2)}"
        else:
            masked_username = "***"
            
        # Create more attractive announcement with emojis and details in HTML format
        announcement = (
            f"🌟 <b>НОВАЯ ПРЕМИУМ-ПОДПИСКА!</b> 🌟\n\n"
            f"✨ Пользователь {masked_username} приобрел:\n"
            f"💎 <b>{order.plan_name}</b>\n"
            f"💰 Стоимость: <b>${formatted_amount}</b>\n\n"
            f"⚡️ Получите доступ к премиальным возможностям Telegram:\n"
            f"✓ Увеличение лимитов\n"
            f"✓ Эксклюзивные наклейки и реакции\n"
            f"✓ Улучшенная загрузка медиа\n"
            f"✓ Премиум значок\n"
            f"✓ И множество других функций!\n\n"
            f"🔥 <b>Присоединяйтесь прямо сейчас!</b>"
        )
        
        # Create attractive inline keyboard with multiple buttons
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        # Main buttons
        order_button = types.InlineKeyboardButton("💎 Получить Premium", url=f"https://t.me/{bot.get_me().username}?start=premium")
        price_button = types.InlineKeyboardButton("💰 Цены и планы", url=f"https://t.me/{bot.get_me().username}?start=prices")
        
        # Information buttons
        features_button = types.InlineKeyboardButton("✨ Возможности", url=f"https://t.me/{bot.get_me().username}?start=features")
        support_button = types.InlineKeyboardButton("🆘 Поддержка", url=f"https://t.me/{bot.get_me().username}?start=support")
        
        # Add buttons in two rows
        markup.add(order_button, price_button)
        markup.add(features_button, support_button)
        
        bot.send_message(
            public_channel,
            announcement,
            parse_mode="HTML",
            reply_markup=markup
        )
        logger.info(f"Purchase announcement sent to public channel: {public_channel}")
    except Exception as e:
        logger.error(f"Error sending purchase announcement to public channel: {e}")

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

def send_broadcast_message(broadcast_id):
    """
    Send a broadcast message to all users
    This function is meant to be run in a background thread
    """
    from models import BroadcastMessage
    from app import app, db
    import time
    
    try:
        # Get the broadcast message from the database
        with app.app_context():
            broadcast = BroadcastMessage.query.get(broadcast_id)
            if not broadcast:
                logger.error(f"Broadcast message {broadcast_id} not found")
                return False
                
            # Update status to sending
            broadcast.status = "SENDING"
            db.session.commit()
            
            # Get all users
            users = db.session.query(User).all()
            total_users = len(users)
            sent_count = 0
            failed_count = 0
            
            logger.info(f"Starting broadcast message {broadcast_id} to {total_users} users")
            
            # Send the message to all users
            for user in users:
                try:
                    # Send the message
                    bot.send_message(
                        chat_id=user.telegram_id,
                        text=broadcast.message_text,
                        parse_mode="Markdown"
                    )
                    sent_count += 1
                    
                    # Update the broadcast stats periodically (every 10 users)
                    if sent_count % 10 == 0:
                        broadcast.sent_count = sent_count
                        broadcast.failed_count = failed_count
                        db.session.commit()
                        
                    # Add a small delay to avoid rate limiting
                    time.sleep(0.1)
                except Exception as e:
                    logger.error(f"Error sending broadcast to user {user.telegram_id}: {str(e)}")
                    failed_count += 1
            
            # Update final stats
            broadcast.sent_count = sent_count
            broadcast.failed_count = failed_count
            broadcast.status = "COMPLETED"
            broadcast.completed_at = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"Broadcast message {broadcast_id} completed: {sent_count} sent, {failed_count} failed")
            return True
    except Exception as e:
        logger.error(f"Error processing broadcast message {broadcast_id}: {str(e)}")
        logger.exception(e)
        
        # Update status to failed
        try:
            with app.app_context():
                broadcast = BroadcastMessage.query.get(broadcast_id)
                if broadcast:
                    broadcast.status = "FAILED"
                    db.session.commit()
        except Exception as update_err:
            logger.error(f"Error updating broadcast status: {str(update_err)}")
            
        return False

if __name__ == "__main__":
    logger.info("Bot script started directly")
    
    # Check if bot is enabled in config
    if config_manager.get_config_value("bot_enabled", default=False):
        logger.info("Bot is enabled, starting in polling mode")
        start_polling()
    else:
        logger.warning("Bot is disabled in configuration. Enable it from admin panel.")
