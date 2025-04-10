import json
import logging
import os
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, current_app
from werkzeug.security import check_password_hash

from app import db
from models import User, Order, AdminUser
import config_manager
from nowpayments import NowPayments

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Blueprint for API routes
api_bp = Blueprint('api', __name__, url_prefix='/api')

# API key authentication middleware
def require_api_key(view_func):
    def decorated(*args, **kwargs):
        # Get API key from header
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({'error': 'API key is required'}), 401
            
        # Check if API key is valid
        admin_user = db.session.query(AdminUser).filter_by(api_key_hash=api_key).first()
        
        if not admin_user:
            return jsonify({'error': 'Invalid API key'}), 401
            
        return view_func(*args, **kwargs)
        
    # Rename the function to avoid naming conflicts
    decorated.__name__ = view_func.__name__
    return decorated

# Helper function to generate order ID
def generate_order_id():
    """Generate a random 5-digit order ID"""
    return str(uuid.uuid4().int)[:5]

# API endpoint to create a new premium order
@api_bp.route('/premium/order', methods=['POST'])
@require_api_key
def create_premium_order():
    try:
        # Get request data
        data = request.json
        
        if not data:
            return jsonify({'error': 'Invalid request data'}), 400
            
        # Validate required fields
        required_fields = ['telegram_username', 'plan_id']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
                
        telegram_username = data['telegram_username']
        plan_id = data['plan_id']
        
        # Clean up username (ensure it starts with @)
        if not telegram_username.startswith('@'):
            telegram_username = f"@{telegram_username}"
            
        # Get plan details
        plan = config_manager.get_plan_by_id(plan_id)
        if not plan:
            return jsonify({'error': f'Invalid plan ID: {plan_id}'}), 400
            
        # Check if user exists, create if not
        user = db.session.query(User).filter_by(username=telegram_username).first()
        
        if not user:
            # Create a new user
            user = User(
                telegram_id=f"api_{uuid.uuid4().hex[:10]}",
                username=telegram_username,
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', '')
            )
            db.session.add(user)
            db.session.commit()
            
        # Create order with initial PENDING status
        order_id = generate_order_id()
        order = Order(
            order_id=order_id,
            user_id=user.id,
            plan_id=plan['id'],
            plan_name=plan['name'],
            amount=plan['price'],
            currency='USD',
            status='PENDING',
            telegram_username=telegram_username,
            created_at=datetime.utcnow()
        )
        
        db.session.add(order)
        db.session.commit()
        
        # Generate payment URL via NowPayments
        api_key = config_manager.get_config_value('nowpayments_api_key')
        if not api_key:
            return jsonify({'error': 'Payment gateway API key not configured'}), 500
            
        payment_client = NowPayments(api_key)
        
        # Set the preferred cryptocurrency (default to TRX)
        crypto_currency = data.get('crypto_currency', 'TRX')
        
        # Check if we should use automated or manual process
        # We'll first check if the credit is sufficient with the supplier
        try:
            # First, create the order in pending state
            order.status = 'PENDING'
            db.session.commit()
            
            # Check supplier credit status (this would be an API call to your supplier)
            # For now, we'll use a simplified approach
            # In a real implementation, you'd call the supplier's API to check credit
            
            # Flag to determine if we have sufficient credit with supplier
            # For this demo, we'll use a config value that can be toggled in admin panel
            has_sufficient_credit = config_manager.get_config_value('has_sufficient_credit', False)
            
            if has_sufficient_credit:
                # If we have sufficient credit, proceed with automated order
                payment_result = payment_client.create_payment(
                    price=plan['price'],
                    currency='USD',
                    pay_currency=crypto_currency,
                    order_id=order_id,
                    order_description=f"Telegram Premium: {plan['name']} for {telegram_username}"
                )
                
                if 'payment_id' in payment_result and 'pay_address' in payment_result:
                    # Update order with payment details
                    order.payment_id = payment_result['payment_id']
                    order.payment_url = payment_result.get('invoice_url', '')
                    order.status = 'AWAITING_PAYMENT'
                    db.session.commit()
                    
                    # Prepare the response
                    response = {
                        'success': True,
                        'order_id': order.order_id,
                        'plan_name': plan['name'],
                        'amount': plan['price'],
                        'currency': 'USD',
                        'crypto_amount': payment_result.get('pay_amount', 0),
                        'crypto_currency': crypto_currency,
                        'payment_address': payment_result.get('pay_address', ''),
                        'payment_id': payment_result['payment_id'],
                        'status': 'AWAITING_PAYMENT',
                        'created_at': order.created_at.isoformat()
                    }
                    
                    return jsonify(response), 201
                else:
                    order.status = 'ERROR'
                    db.session.commit()
                    return jsonify({'error': 'Failed to create payment', 'details': payment_result}), 500
            else:
                # If we don't have sufficient credit, mark for manual processing
                order.status = 'AWAITING_CREDIT'
                order.admin_notes = "Awaiting admin to increase supplier credit and process manually."
                db.session.commit()
                
                # Still return a success response but with different status
                response = {
                    'success': True,
                    'order_id': order.order_id,
                    'plan_name': plan['name'],
                    'amount': plan['price'],
                    'currency': 'USD',
                    'status': 'AWAITING_CREDIT',
                    'message': 'Order received but awaiting manual processing due to supplier credit check.',
                    'created_at': order.created_at.isoformat()
                }
                
                return jsonify(response), 201
                
        except Exception as e:
            logger.error(f"Payment creation error: {str(e)}")
            order.status = 'ERROR'
            db.session.commit()
            return jsonify({'error': f'Payment gateway error: {str(e)}'}), 500
            
    except Exception as e:
        logger.error(f"API error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

# API endpoint to get order status
@api_bp.route('/premium/order/<order_id>', methods=['GET'])
@require_api_key
def get_order_status(order_id):
    try:
        # Get order from database
        order = db.session.query(Order).filter_by(order_id=order_id).first()
        
        if not order:
            return jsonify({'error': 'Order not found'}), 404
            
        # Prepare the response
        response = {
            'order_id': order.order_id,
            'telegram_username': order.telegram_username,
            'plan_name': order.plan_name,
            'amount': float(order.amount),
            'currency': order.currency,
            'status': order.status,
            'created_at': order.created_at.isoformat(),
            'payment_id': order.payment_id
        }
        
        # Add additional fields if available
        if order.expires_at:
            response['expires_at'] = order.expires_at.isoformat()
            
        if order.updated_at:
            response['updated_at'] = order.updated_at.isoformat()
            
        if order.activation_link:
            response['activation_link'] = order.activation_link
            
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"API error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

# API endpoint to list all orders (with pagination)
@api_bp.route('/premium/orders', methods=['GET'])
@require_api_key
def list_orders():
    try:
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        status = request.args.get('status')
        
        # Limit per_page to a reasonable number
        if per_page > 100:
            per_page = 100
            
        # Build query
        query = db.session.query(Order)
        
        # Filter by status if provided
        if status:
            query = query.filter(Order.status == status)
            
        # Paginate results
        orders = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page)
        
        # Prepare the response
        response = {
            'total': orders.total,
            'page': page,
            'per_page': per_page,
            'pages': orders.pages,
            'orders': []
        }
        
        for order in orders.items:
            order_data = {
                'order_id': order.order_id,
                'telegram_username': order.telegram_username,
                'plan_name': order.plan_name,
                'amount': float(order.amount),
                'currency': order.currency,
                'status': order.status,
                'created_at': order.created_at.isoformat()
            }
            response['orders'].append(order_data)
            
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"API error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

# Add API key generation for admin users
@api_bp.route('/admin/generate-api-key', methods=['POST'])
def generate_api_key():
    data = request.json
    
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Username and password required'}), 400
        
    # Authenticate admin user
    admin = db.session.query(AdminUser).filter_by(username=data['username']).first()
    
    if not admin or not check_password_hash(admin.password_hash, data['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
        
    # Generate a new API key
    api_key = str(uuid.uuid4())
    
    # Update admin user with API key hash
    admin.api_key_hash = api_key
    db.session.commit()
    
    return jsonify({
        'success': True,
        'api_key': api_key,
        'message': 'API key generated successfully. Keep this key secure!'
    }), 200