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
    status = request.args.get('status', '')
    
    if status:
        orders = Order.query.filter_by(status=status).order_by(Order.created_at.desc()).all()
    else:
        orders = Order.query.order_by(Order.created_at.desc()).all()
        
    return render_template('admin/orders.html', orders=orders, current_status=status)

@app.route('/admin/orders/<order_id>')
@login_required
def admin_order_detail(order_id):
    order = Order.query.filter_by(order_id=order_id).first_or_404()
    payment = PaymentTransaction.query.filter_by(order_id=order.id).first()
    
    return render_template('admin/order_details.html', order=order, payment=payment)

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

@app.route('/webhook/telestars24bot', methods=['POST'])
def telegram_webhook():
    """Endpoint for Telegram webhook, to be used with setWebhook"""
    # This is a placeholder and will be implemented with the telegram bot handler
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
