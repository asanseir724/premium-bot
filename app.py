import os
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, abort, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy.orm import DeclarativeBase

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize database
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key_for_development")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///telegram_premium.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize the database with the app
db.init_app(app)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Import models after db is defined to avoid circular imports
from models import User, Order, PaymentTransaction, AdminUser

# Import API clients
import config_manager
from nowpayments import NowPayments
from callinoo import CallinooAPI
from telegram_premium_service import TelegramPremiumService

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(AdminUser, int(user_id))

# Create the database tables
with app.app_context():
    db.create_all()
    
    # Create a default admin user if none exists
    if not AdminUser.query.filter_by(username="admin").first():
        admin = AdminUser(
            username="admin",
            password_hash=generate_password_hash("admin"),  # Change this in production
            is_super_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        logger.info("Default admin user created")

# Register API Blueprint
from api import api_bp
app.register_blueprint(api_bp)

# API Documentation Route
@app.route('/api/docs')
def api_docs():
    """Public API documentation page"""
    return render_template('api_docs.html')

# Import routes after db is defined
from nowpayments import NowPayments
import config_manager

# Initialize NowPayments API client
nowpayments_api = NowPayments(os.environ.get("NOWPAYMENTS_API_KEY", ""))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = AdminUser.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
def admin_dashboard():
    # Count orders by status
    pending_count = Order.query.filter_by(status='ADMIN_REVIEW').count()
    completed_count = Order.query.filter_by(status='COMPLETED').count()
    cancelled_count = Order.query.filter_by(status='CANCELLED').count()
    
    # Recent orders
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    
    # Count payments
    successful_payments = PaymentTransaction.query.filter_by(status='COMPLETED').count()
    
    return render_template('admin/dashboard.html', 
                           pending_count=pending_count,
                           completed_count=completed_count,
                           cancelled_count=cancelled_count,
                           recent_orders=recent_orders,
                           successful_payments=successful_payments)

@app.route('/admin/orders')
@login_required
def admin_orders():
    # Filter by status
    status = request.args.get('status', '')
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    query = Order.query
    
    # Apply status filter if provided
    if status:
        query = query.filter(Order.status == status)
    
    # Apply search if provided
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Order.order_id.like(search_term),
                Order.telegram_username.like(search_term),
                Order.status.like(search_term),
                Order.plan_name.like(search_term)
            )
        )
    
    # Order by most recent first
    query = query.order_by(Order.created_at.desc())
    
    # Paginate results
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    orders = pagination.items
    
    return render_template(
        'admin/orders.html', 
        orders=orders, 
        pagination=pagination,
        current_status=status,
        search_query=search
    )

@app.route('/admin/orders/<order_id>')
@login_required
def admin_order_detail(order_id):
    order = Order.query.filter_by(order_id=order_id).first_or_404()
    payments = PaymentTransaction.query.filter_by(order_id=order.id).all()
    
    return render_template('admin/order_detail.html', order=order, payments=payments)

@app.route('/admin/orders/<order_id>/approve', methods=['POST'])
@login_required
def admin_approve_order(order_id):
    order = Order.query.filter_by(order_id=order_id).first_or_404()
    
    # Check if we should use Callinoo API for Telegram Premium
    use_callinoo = TelegramPremiumService.is_callinoo_enabled()
    
    # Check if manual activation link is provided
    activation_link = request.form.get('activation_link', '')
    admin_notes = request.form.get('admin_notes', '')
    
    # If Callinoo is enabled and no manual activation link is provided, use Callinoo API
    if use_callinoo and not activation_link:
        try:
            logger.info(f"Using Callinoo API to create Telegram Premium for {order.telegram_username}")
            
            # Create the subscription via Callinoo API
            # We assume monthly subscription for now, can be made configurable later
            result = TelegramPremiumService.create_premium_subscription(
                telegram_username=order.telegram_username,
                period='monthly'  # This could be based on the plan or configurable
            )
            
            if result['success']:
                # Successfully created subscription
                order.activation_link = result.get('activation_link', '')
                callinoo_order_id = result.get('order_id', '')
                
                # Update status and notes
                order.status = 'APPROVED'
                order.updated_at = datetime.utcnow()
                
                # Add API response details to admin notes
                new_note = f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] " + \
                           f"Telegram Premium subscription created via Callinoo API. " + \
                           f"Callinoo Order ID: {callinoo_order_id}"
                
                if admin_notes:
                    order.admin_notes = admin_notes + "\n\n" + new_note
                else:
                    order.admin_notes = new_note
                
                # Add success message
                flash(f'Order {order_id} has been approved and subscription created via Callinoo API', 'success')
            else:
                # API call failed
                error_msg = result.get('message', 'Unknown error')
                logger.error(f"Callinoo API error: {error_msg}")
                
                # Add error details to admin notes
                new_note = f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] " + \
                           f"Failed to create Telegram Premium via Callinoo API: {error_msg}"
                
                if admin_notes:
                    order.admin_notes = admin_notes + "\n\n" + new_note
                else:
                    order.admin_notes = new_note
                
                # Keep original status if API fails
                order.updated_at = datetime.utcnow()
                
                # Add error message
                flash(f'Failed to create subscription via Callinoo API: {error_msg}', 'danger')
                
        except Exception as e:
            logger.exception(f"Error using Callinoo API: {str(e)}")
            
            # Add error details to admin notes
            new_note = f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] " + \
                       f"Error using Callinoo API: {str(e)}"
            
            if admin_notes:
                order.admin_notes = admin_notes + "\n\n" + new_note
            else:
                order.admin_notes = new_note
            
            # Keep original status if exception occurs
            order.updated_at = datetime.utcnow()
            
            # Add error message
            flash(f'Error using Callinoo API: {str(e)}', 'danger')
    else:
        # Standard approval process (manual or Callinoo disabled)
        order.status = 'APPROVED'
        order.updated_at = datetime.utcnow()
        order.admin_notes = admin_notes
        
        # Set manual activation link if provided
        if activation_link:
            order.activation_link = activation_link
            
        flash(f'Order {order_id} has been approved', 'success')
    
    # Save all changes
    db.session.commit()
    
    # Trigger notification to user via Telegram bot (will be implemented in run_telegram_bot.py)
    # This is a placeholder and will be connected to the actual bot
    
    return redirect(url_for('admin_order_detail', order_id=order_id))

@app.route('/admin/orders/<order_id>/reject', methods=['POST'])
@login_required
def admin_reject_order(order_id):
    order = Order.query.filter_by(order_id=order_id).first_or_404()
    
    # Update order status
    order.status = 'REJECTED'
    order.updated_at = datetime.utcnow()
    order.admin_notes = request.form.get('admin_notes', '')
    
    db.session.commit()
    
    flash(f'Order {order_id} has been rejected', 'danger')
    
    # Trigger notification to user via Telegram bot (will be implemented in run_telegram_bot.py)
    # This is a placeholder and will be connected to the actual bot
    
    return redirect(url_for('admin_order_detail', order_id=order_id))

@app.route('/admin/plans')
@login_required
def admin_plans():
    plans = config_manager.get_subscription_plans()
    return render_template('admin/plans.html', plans=plans)

@app.route('/admin/plans/update', methods=['POST'])
@login_required
def admin_update_plan():
    plan_id = request.form.get('plan_id')
    plan_name = request.form.get('plan_name')
    plan_description = request.form.get('plan_description')
    plan_price = float(request.form.get('plan_price'))
    
    config_manager.update_subscription_plan(plan_id, plan_name, plan_description, plan_price)
    
    flash(f'Plan {plan_name} has been updated', 'success')
    return redirect(url_for('admin_plans'))

@app.route('/webhook/payment/callback', methods=['POST'])
def payment_webhook():
    logger.debug(f"Received payment webhook: {request.json}")
    
    if not request.json:
        return jsonify({"status": "error", "message": "No data provided"}), 400
    
    # Process the payment notification
    payment_data = request.json
    
    # Find the related payment transaction
    payment_id = payment_data.get('payment_id')
    if not payment_id:
        return jsonify({"status": "error", "message": "No payment_id provided"}), 400
        
    transaction = PaymentTransaction.query.filter_by(payment_id=payment_id).first()
    if not transaction:
        return jsonify({"status": "error", "message": "Payment not found"}), 404
    
    # Update transaction status
    transaction.status = payment_data.get('payment_status', 'UNKNOWN')
    transaction.ipn_data = payment_data
    transaction.updated_at = datetime.utcnow()
    
    if transaction.status == 'COMPLETED':
        transaction.completed_at = datetime.utcnow()
        
        # Update the related order
        order = Order.query.get(transaction.order_id)
        if order:
            order.status = 'PAYMENT_RECEIVED'
            order.updated_at = datetime.utcnow()
    
    db.session.commit()
    logger.info(f"Updated payment transaction {payment_id} to status {transaction.status}")
    
    return jsonify({"status": "success"})

# Admin routes for new admin panel sections
@app.route('/admin/admins')
@login_required
def admin_admins():
    # Get list of bot admins from config
    bot_admins = config_manager.get_bot_admins()
    # Get list of web admin users
    web_admins = AdminUser.query.all()
    
    return render_template('admin/admins.html', bot_admins=bot_admins, web_admins=web_admins)

@app.route('/admin/admins/add_bot_admin', methods=['POST'])
@login_required
def admin_add_bot_admin():
    admin_id = request.form.get('admin_id')
    if admin_id:
        success = config_manager.add_bot_admin(admin_id)
        if success:
            flash(f'Bot admin {admin_id} has been added', 'success')
        else:
            flash(f'Bot admin {admin_id} already exists', 'warning')
    else:
        flash('Admin ID is required', 'danger')
    
    return redirect(url_for('admin_admins'))

@app.route('/admin/admins/remove_bot_admin/<admin_id>', methods=['POST'])
@login_required
def admin_remove_bot_admin(admin_id):
    if admin_id:
        success = config_manager.remove_bot_admin(admin_id)
        if success:
            flash(f'Bot admin {admin_id} has been removed', 'success')
        else:
            flash(f'Bot admin {admin_id} not found', 'danger')
    
    return redirect(url_for('admin_admins'))

@app.route('/admin/admins/add_web_admin', methods=['POST'])
@login_required
def admin_add_web_admin():
    username = request.form.get('username')
    password = request.form.get('password')
    is_super_admin = 'is_super_admin' in request.form
    
    if not username or not password:
        flash('Username and password are required', 'danger')
        return redirect(url_for('admin_admins'))
    
    existing_admin = AdminUser.query.filter_by(username=username).first()
    if existing_admin:
        flash(f'Admin user {username} already exists', 'warning')
        return redirect(url_for('admin_admins'))
    
    new_admin = AdminUser(
        username=username,
        password_hash=generate_password_hash(password),
        is_super_admin=is_super_admin
    )
    
    db.session.add(new_admin)
    db.session.commit()
    
    flash(f'Admin user {username} has been added', 'success')
    return redirect(url_for('admin_admins'))

@app.route('/admin/admins/remove_web_admin/<int:admin_id>', methods=['POST'])
@login_required
def admin_remove_web_admin(admin_id):
    # Make sure the current user is a super admin
    if not current_user.is_super_admin:
        flash('Only super admins can remove admin users', 'danger')
        return redirect(url_for('admin_admins'))
    
    # Don't allow deleting self
    if current_user.id == admin_id:
        flash('You cannot remove yourself', 'danger')
        return redirect(url_for('admin_admins'))
    
    admin = AdminUser.query.get(admin_id)
    if not admin:
        flash('Admin user not found', 'danger')
        return redirect(url_for('admin_admins'))
    
    db.session.delete(admin)
    db.session.commit()
    
    flash(f'Admin user {admin.username} has been removed', 'success')
    return redirect(url_for('admin_admins'))

@app.route('/admin/channels')
@login_required
def admin_channels():
    # Use the dedicated channel getter functions
    admin_channel = config_manager.get_admin_channel()
    public_channel = config_manager.get_public_channel()
    notification_enabled = config_manager.get_config_value('notification_enabled', False)
    
    return render_template('admin/channels.html', 
                           admin_channel=admin_channel, 
                           public_channel=public_channel,
                           notification_enabled=notification_enabled)

@app.route('/admin/channels/update', methods=['POST'])
@login_required
def admin_update_channels():
    admin_channel = request.form.get('admin_channel')
    public_channel = request.form.get('public_channel')
    notification_enabled = 'notification_enabled' in request.form
    
    # Save to config using the dedicated functions
    config_manager.set_admin_channel(admin_channel)
    config_manager.set_public_channel(public_channel)
    config_manager.set_config_value('notification_enabled', notification_enabled)
    
    flash('Channel settings have been updated successfully', 'success')
    return redirect(url_for('admin_channels'))

@app.route('/admin/webhooks')
@login_required
def admin_webhooks():
    # Check if webhook is set up
    telegram_webhook_url = request.host_url.rstrip('/') + url_for('telegram_webhook')
    payment_webhook_url = request.host_url.rstrip('/') + url_for('payment_webhook')
    
    # Get admin API key if exists
    api_key = current_user.api_key_hash
    
    # Generate Premium API URL for documentation
    premium_api_url = request.host_url.rstrip('/') + url_for('api.create_premium_order')
    
    return render_template('admin/webhooks.html', 
                           telegram_webhook_url=telegram_webhook_url,
                           payment_webhook_url=payment_webhook_url,
                           api_key=api_key,
                           premium_api_url=premium_api_url)

@app.route('/admin/webhooks/generate_api_key', methods=['POST'])
@login_required
def admin_generate_api_key():
    """Generate a new API key for the current admin user"""
    import uuid
    
    # Generate a new API key
    api_key = str(uuid.uuid4())
    
    # Update the current user's API key
    current_user.api_key_hash = api_key
    db.session.commit()
    
    flash('New API key has been generated. Keep it secure!', 'success')
    return redirect(url_for('admin_webhooks'))

@app.route('/admin/support')
@login_required
def admin_support():
    # Get current support contact
    support_contact = config_manager.get_support_contact()
    return render_template('admin/support.html', support_contact=support_contact)

@app.route('/admin/support/update', methods=['POST'])
@login_required
def admin_update_support():
    support_contact = request.form.get('support_contact')
    
    if support_contact:
        config_manager.set_support_contact(support_contact)
        flash('Support contact has been updated', 'success')
    else:
        flash('Support contact is required', 'danger')
    
    return redirect(url_for('admin_support'))

@app.route('/admin/orders/<order_id>/process_manual', methods=['POST'])
@login_required
def admin_process_manual_order(order_id):
    """Process an order manually after credit has been added to supplier account"""
    try:
        order = Order.query.filter_by(order_id=order_id).first_or_404()
        
        # Ensure order is in the right state
        if order.status != 'AWAITING_CREDIT':
            flash(f'Order cannot be processed: current status is {order.status}', 'danger')
            return redirect(url_for('admin_order_detail', order_id=order_id))
            
        # Check if admin confirmed credit
        credit_confirmed = 'credit_confirmed' in request.form
        if not credit_confirmed:
            flash('You must confirm that credit has been added to supplier account', 'danger')
            return redirect(url_for('admin_order_detail', order_id=order_id))
            
        # Update the order status
        order.status = 'SUPPLIER_PROCESSING'
        order.updated_at = datetime.utcnow()
        order.admin_notes = (order.admin_notes or '') + "\n" + f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Order sent to supplier for processing."
        db.session.commit()
        
        # Here you would make the actual API call to your supplier
        # This is where you'd integrate with the supplier's API
        
        flash(f'Order {order_id} has been sent to supplier for processing', 'success')
        return redirect(url_for('admin_order_detail', order_id=order_id))
    except Exception as e:
        logger.error(f"Error processing manual order: {str(e)}")
        logger.exception(e)
        flash(f'Error processing order: {str(e)}', 'danger')
        return redirect(url_for('admin_order_detail', order_id=order_id))

@app.route('/admin/orders/<order_id>/confirm_supplier', methods=['POST'])
@login_required
def admin_confirm_supplier_complete(order_id):
    """Confirm that the supplier has completed the order"""
    try:
        order = Order.query.filter_by(order_id=order_id).first_or_404()
        
        # Ensure order is in the right state
        if order.status != 'SUPPLIER_PROCESSING':
            flash(f'Order cannot be confirmed: current status is {order.status}', 'danger')
            return redirect(url_for('admin_order_detail', order_id=order_id))
            
        # Get activation link
        activation_link = request.form.get('activation_link', '')
        if not activation_link:
            flash('Activation link is required', 'danger')
            return redirect(url_for('admin_order_detail', order_id=order_id))
        
        # Update order status
        order.status = 'APPROVED'
        order.updated_at = datetime.utcnow()
        order.activation_link = activation_link
        order.admin_notes = (order.admin_notes or '') + "\n" + f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] Order confirmed as completed by supplier."
        db.session.commit()
        
        # Send notification to customer via Telegram
        try:
            from run_telegram_bot import notify_customer_about_approval
            notify_customer_about_approval(order)
        except Exception as notify_err:
            logger.error(f"Error notifying customer: {str(notify_err)}")
            
        flash(f'Order {order_id} has been marked as completed and customer has been notified', 'success')
        return redirect(url_for('admin_order_detail', order_id=order_id))
    except Exception as e:
        logger.error(f"Error confirming supplier completion: {str(e)}")
        logger.exception(e)
        flash(f'Error confirming completion: {str(e)}', 'danger')
        return redirect(url_for('admin_order_detail', order_id=order_id))

@app.route('/admin/callinoo')
@login_required
def admin_callinoo():
    """Admin page for managing Callinoo API settings"""
    # Get current Callinoo API settings
    callinoo_token = config_manager.get_config_value('callinoo_token', '')
    use_callinoo_for_premium = config_manager.get_config_value('use_callinoo_for_premium', False)
    
    # Initialize callinoo client if token exists
    callinoo_balance = None
    callinoo_services = None
    if callinoo_token:
        try:
            callinoo_client = CallinooAPI(token=callinoo_token)
            callinoo_balance = callinoo_client.get_balance()
            if callinoo_balance and 'error' not in callinoo_balance:
                session['callinoo_balance'] = callinoo_balance
            else:
                callinoo_balance = session.get('callinoo_balance')
                
            # Get services list if available
            try:
                callinoo_services = callinoo_client.get_services()
                if callinoo_services and 'error' not in callinoo_services:
                    session['callinoo_services'] = callinoo_services
                else:
                    callinoo_services = session.get('callinoo_services')
            except:
                callinoo_services = session.get('callinoo_services')
        except Exception as e:
            logger.error(f"Error initializing Callinoo client: {e}")
            flash(f"Could not connect to Callinoo API: {str(e)}", "danger")
    
    return render_template('admin/callinoo.html', 
                           callinoo_token=callinoo_token, 
                           use_callinoo_for_premium=use_callinoo_for_premium,
                           callinoo_balance=callinoo_balance,
                           callinoo_services=callinoo_services)

@app.route('/admin/callinoo/update', methods=['POST'])
@login_required
def admin_update_callinoo():
    """Update Callinoo API settings"""
    callinoo_token = request.form.get('callinoo_token')
    use_callinoo_for_premium = 'use_callinoo_for_premium' in request.form
    
    # Save settings to config
    config_manager.set_config_value('callinoo_token', callinoo_token)
    config_manager.set_config_value('use_callinoo_for_premium', use_callinoo_for_premium)
    
    # Try to initialize the client to verify token
    if callinoo_token:
        try:
            callinoo_client = CallinooAPI(token=callinoo_token)
            balance = callinoo_client.get_balance()
            if 'error' not in balance:
                flash("Callinoo API settings updated successfully and connection verified!", "success")
            else:
                flash(f"Callinoo API settings updated but connection failed: {balance.get('error', 'Unknown error')}", "warning")
        except Exception as e:
            flash(f"Callinoo API settings updated but connection failed: {str(e)}", "warning")
    else:
        flash("Callinoo API settings updated. Token is empty, integration is disabled.", "info")
    
    return redirect(url_for('admin_callinoo'))

@app.route('/admin/callinoo/check_balance', methods=['POST'])
@login_required
def admin_check_callinoo_balance():
    """Check current balance on Callinoo API"""
    callinoo_token = config_manager.get_config_value('callinoo_token', '')
    
    if not callinoo_token:
        flash("No Callinoo API token configured", "danger")
        return redirect(url_for('admin_callinoo'))
    
    try:
        callinoo_client = CallinooAPI(token=callinoo_token)
        balance = callinoo_client.get_balance()
        
        if 'error' not in balance:
            session['callinoo_balance'] = balance
            flash(f"Current balance: {balance.get('balance')} {balance.get('currency')}", "success")
        else:
            flash(f"Failed to check balance: {balance.get('error', 'Unknown error')}", "danger")
    except Exception as e:
        flash(f"Error checking Callinoo balance: {str(e)}", "danger")
    
    return redirect(url_for('admin_callinoo'))

@app.route('/admin/callinoo/test_connection', methods=['POST'])
@login_required
def admin_test_callinoo_connection():
    """Test connection to Callinoo API"""
    callinoo_token = config_manager.get_config_value('callinoo_token', '')
    
    if not callinoo_token:
        flash("No Callinoo API token configured", "danger")
        return redirect(url_for('admin_callinoo'))
    
    try:
        callinoo_client = CallinooAPI(token=callinoo_token)
        services = callinoo_client.get_services()
        
        if 'error' not in services:
            session['callinoo_services'] = services
            flash(f"Successfully connected to Callinoo API. Found {len(services)} services.", "success")
        else:
            flash(f"Connection failed: {services.get('error', 'Unknown error')}", "danger")
    except Exception as e:
        flash(f"Error connecting to Callinoo API: {str(e)}", "danger")
    
    return redirect(url_for('admin_callinoo'))

@app.route('/admin/bot_settings')
@login_required
def admin_bot_settings():
    # Get current bot token and other settings
    bot_token = config_manager.get_config_value('bot_token', '')
    nowpayments_api_key = config_manager.get_config_value('nowpayments_api_key', '')
    bot_enabled = config_manager.get_config_value('bot_enabled', False)
    has_sufficient_credit = config_manager.get_config_value('has_sufficient_credit', False)
    
    return render_template('admin/bot_settings.html', 
                           bot_token=bot_token, 
                           nowpayments_api_key=nowpayments_api_key,
                           bot_enabled=bot_enabled,
                           has_sufficient_credit=has_sufficient_credit)

@app.route('/admin/bot_settings/update', methods=['POST'])
@login_required
def admin_update_bot_settings():
    bot_token = request.form.get('bot_token', '')
    nowpayments_api_key = request.form.get('nowpayments_api_key', '')
    bot_enabled = 'bot_enabled' in request.form
    has_sufficient_credit = 'has_sufficient_credit' in request.form
    
    # Save settings to config
    config_manager.set_config_value('bot_token', bot_token)
    config_manager.set_config_value('nowpayments_api_key', nowpayments_api_key)
    config_manager.set_config_value('bot_enabled', bot_enabled)
    config_manager.set_config_value('has_sufficient_credit', has_sufficient_credit)
    
    # Log the supplier credit status change
    if has_sufficient_credit:
        logger.info("Supplier credit set to SUFFICIENT")
    else:
        logger.info("Supplier credit set to INSUFFICIENT")
    
    flash('Bot settings have been updated', 'success')
    return redirect(url_for('admin_bot_settings'))

@app.route('/admin/bot_settings/start', methods=['POST'])
@login_required
def admin_start_bot():
    # Logic to start the bot
    try:
        # Import the required function
        import subprocess
        import sys
        
        # Set bot as enabled in config
        config_manager.set_config_value('bot_enabled', True)
        app.logger.info("Bot enabled in config")
        
        # Start the bot in a separate process
        # In this implementation, we're starting it in the background
        bot_token = config_manager.get_config_value('bot_token')
        if not bot_token:
            flash('Bot token is required to start the bot', 'danger')
            return redirect(url_for('admin_bot_settings'))
        
        # Check if we're in a subprocess already to avoid nested subprocesses
        is_subprocess = os.environ.get('BOT_SUBPROCESS') == '1'
        if not is_subprocess:
            app.logger.info("Starting bot in a separate process")
            env = os.environ.copy()
            env['BOT_SUBPROCESS'] = '1'
            
            # Run the bot script as a separate process
            subprocess.Popen([sys.executable, 'start_bot.py'], 
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            env=env)
            
            flash('Bot has been started in background', 'success')
        else:
            app.logger.warning("Already in a subprocess, not starting another one")
            flash('Bot process already running', 'warning')
    except Exception as e:
        app.logger.error(f"Error starting bot: {str(e)}")
        app.logger.exception(e)
        flash(f'Failed to start bot: {str(e)}', 'danger')
    
    return redirect(url_for('admin_bot_settings'))

@app.route('/admin/bot_settings/stop', methods=['POST'])
@login_required
def admin_stop_bot():
    # Logic to stop the bot
    try:
        # Set bot as disabled in config
        config_manager.set_config_value('bot_enabled', False)
        app.logger.info("Bot disabled in config")
        
        # In a real production environment, you would need a proper process management
        # solution (like supervisord) to control the bot process
        # For now, we'll just rely on the bot checking the enabled flag in config
        
        flash('Bot has been disabled. The process will terminate on its next check cycle.', 'success')
    except Exception as e:
        app.logger.error(f"Error stopping bot: {str(e)}")
        app.logger.exception(e)
        flash(f'Failed to stop bot: {str(e)}', 'danger')
    
    return redirect(url_for('admin_bot_settings'))

@app.route('/admin/bot_settings/set_webhook', methods=['POST'])
@login_required
def admin_set_webhook():
    # Logic to set webhook for the bot
    try:
        bot_token = config_manager.get_config_value('bot_token', '')
        if not bot_token:
            flash('Bot token is required to set webhook', 'danger')
            return redirect(url_for('admin_bot_settings'))
        
        webhook_url = request.host_url.rstrip('/') + url_for('telegram_webhook')
        
        # This is a placeholder. In a real app, you'd make an API call to Telegram
        # For example: https://api.telegram.org/bot<token>/setWebhook?url=<webhook_url>
        import requests
        response = requests.get(f'https://api.telegram.org/bot{bot_token}/setWebhook?url={webhook_url}')
        
        if response.status_code == 200 and response.json().get('ok'):
            flash('Webhook has been set successfully', 'success')
        else:
            flash(f'Failed to set webhook: {response.json().get("description", "Unknown error")}', 'danger')
    except Exception as e:
        flash(f'Failed to set webhook: {str(e)}', 'danger')
    
    return redirect(url_for('admin_bot_settings'))

@app.route('/webhook/telestars24bot', methods=['POST'])
def telegram_webhook():
    """Endpoint for Telegram webhook, to be used with setWebhook"""
    try:
        # Import telegram bot logic
        from run_telegram_bot import process_webhook_update
        
        # Get the update data from Telegram
        update_json = request.get_json()
        if not update_json:
            app.logger.error("Empty update received in webhook")
            return jsonify({"status": "error", "message": "Empty update"})
        
        # Log webhook request for debugging
        app.logger.debug(f"Received Telegram update: {update_json}")
        
        # Process the update
        result = process_webhook_update(update_json)
        if result:
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": "Failed to process update"})
    except Exception as e:
        app.logger.error(f"Error in webhook handler: {str(e)}")
        app.logger.exception(e)
        return jsonify({"status": "error", "message": str(e)})

@app.route('/webhook/nowpayments/ipn', methods=['POST'])
def nowpayments_ipn_webhook():
    """Endpoint for NowPayments IPN (Instant Payment Notification)"""
    try:
        # Verify that the request contains JSON data
        if not request.is_json:
            app.logger.error("Invalid payment webhook: Not JSON data")
            return jsonify({"status": "error", "message": "Invalid content type, expected JSON"}), 400
        
        # Get webhook data
        ipn_data = request.get_json()
        app.logger.info(f"Received payment IPN: {ipn_data}")
        
        # Verify IPN authenticity
        api_key = config_manager.get_config_value('nowpayments_api_key', '')
        if not api_key:
            app.logger.error("Cannot process IPN: NowPayments API key not set")
            return jsonify({"status": "error", "message": "API key not configured"}), 500
            
        # Initialize the API client
        from nowpayments import NowPayments
        nowpayments_api = NowPayments(api_key=api_key)
        
        # Verify the IPN signature
        is_valid = nowpayments_api.verify_ipn_callback(ipn_data)
        if not is_valid:
            app.logger.error("Invalid IPN signature")
            return jsonify({"status": "error", "message": "Invalid IPN signature"}), 400
            
        # Process the payment update
        payment_id = ipn_data.get('payment_id')
        payment_status = ipn_data.get('payment_status')
        
        if not payment_id or not payment_status:
            app.logger.error(f"Missing payment information in IPN: {ipn_data}")
            return jsonify({"status": "error", "message": "Missing payment information"}), 400
            
        app.logger.info(f"Processing payment update: Payment ID {payment_id}, Status: {payment_status}")
        
        # Find the payment transaction
        with db.session() as session:
            transaction = session.query(PaymentTransaction).filter_by(payment_id=payment_id).first()
            
            if not transaction:
                app.logger.error(f"Payment transaction not found: {payment_id}")
                return jsonify({"status": "error", "message": "Payment transaction not found"}), 404
                
            # Update transaction status and data
            transaction.status = payment_status
            transaction.ipn_data = ipn_data
            
            if payment_status in ["FINISHED", "CONFIRMED"]:
                transaction.completed_at = datetime.utcnow()
                
                # Update the corresponding order
                order = session.query(Order).get(transaction.order_id)
                if order:
                    previous_status = order.status
                    order.status = "PAYMENT_RECEIVED"
                    order.updated_at = datetime.utcnow()
                    
                    # Save changes
                    session.commit()
                    
                    app.logger.info(f"Payment confirmed for order #{order.order_id}: Status changed from {previous_status} to PAYMENT_RECEIVED")
                    
                    # Optionally notify admins about the payment
                    try:
                        from run_telegram_bot import notify_admins_about_payment
                        notify_admins_about_payment(order, transaction)
                    except Exception as notify_error:
                        app.logger.error(f"Error notifying admins: {str(notify_error)}")
                else:
                    app.logger.error(f"Order not found for payment: {payment_id}")
                    return jsonify({"status": "error", "message": "Order not found"}), 404
            else:
                # For other statuses, just update the transaction
                session.commit()
                app.logger.info(f"Payment status updated: {payment_id} to {payment_status}")
            
            return jsonify({"status": "success", "message": f"Payment updated: {payment_status}"})
    except Exception as e:
        app.logger.error(f"Error processing payment webhook: {str(e)}")
        app.logger.exception(e)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
