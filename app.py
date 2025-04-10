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
    
    # Update order status
    order.status = 'APPROVED'
    order.updated_at = datetime.utcnow()
    order.admin_notes = request.form.get('admin_notes', '')
    
    # Set activation link if provided
    activation_link = request.form.get('activation_link', '')
    if activation_link:
        order.activation_link = activation_link
    
    db.session.commit()
    
    flash(f'Order {order_id} has been approved', 'success')
    
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
    # Default values if not in config
    admin_channel = config_manager.get_config_value('admin_channel', '@admin_channel')
    public_channel = config_manager.get_config_value('public_channel', '@public_channel')
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
    
    # Save to config
    config_manager.set_config_value('admin_channel', admin_channel)
    config_manager.set_config_value('public_channel', public_channel)
    config_manager.set_config_value('notification_enabled', notification_enabled)
    
    flash('Channel settings have been updated', 'success')
    return redirect(url_for('admin_channels'))

@app.route('/admin/webhooks')
@login_required
def admin_webhooks():
    # Check if webhook is set up
    telegram_webhook_url = request.host_url.rstrip('/') + url_for('telegram_webhook')
    payment_webhook_url = request.host_url.rstrip('/') + url_for('payment_webhook')
    
    return render_template('admin/webhooks.html', 
                           telegram_webhook_url=telegram_webhook_url,
                           payment_webhook_url=payment_webhook_url)

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

@app.route('/webhook/telestars24bot', methods=['POST'])
def telegram_webhook():
    """Endpoint for Telegram webhook, to be used with setWebhook"""
    # This is a placeholder and will be implemented with the telegram bot handler
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
