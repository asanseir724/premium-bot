"""
Telegram Premium Subscription API - Python Client Example

This script demonstrates how to use the Telegram Premium Subscription API
to create premium subscription orders programmatically.

Requirements:
- requests library: pip install requests
"""

import json
import requests

class TelegramPremiumClient:
    """
    Python client for the Telegram Premium Subscription API
    """
    
    def __init__(self, base_url, api_key):
        """
        Initialize the client with the API base URL and API key.
        
        Args:
            base_url (str): The base URL of the API, e.g., 'https://your-domain.com'
            api_key (str): Your API key for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'Content-Type': 'application/json',
            'X-API-Key': api_key
        }
    
    def create_premium_order(self, telegram_username, plan_id, crypto_currency='TRX'):
        """
        Create a new premium subscription order.
        
        Args:
            telegram_username (str): The Telegram username of the customer (with or without @)
            plan_id (str): The ID of the subscription plan
            crypto_currency (str, optional): The cryptocurrency for payment. Defaults to 'TRX'.
            
        Returns:
            dict: The order details including payment information
        """
        # Ensure username starts with @
        if not telegram_username.startswith('@'):
            telegram_username = f'@{telegram_username}'
            
        # Prepare request data
        data = {
            'telegram_username': telegram_username,
            'plan_id': plan_id,
            'crypto_currency': crypto_currency
        }
        
        # Make the API request
        url = f'{self.base_url}/api/premium/order'
        response = requests.post(url, headers=self.headers, json=data)
        
        # Raise exception for HTTP errors
        response.raise_for_status()
        
        # Return the order details
        return response.json()
    
    def get_order_status(self, order_id):
        """
        Get the status of an existing order.
        
        Args:
            order_id (str): The order ID to check
            
        Returns:
            dict: The order details including current status
        """
        url = f'{self.base_url}/api/premium/order/{order_id}'
        response = requests.get(url, headers=self.headers)
        
        # Raise exception for HTTP errors
        response.raise_for_status()
        
        # Return the order details
        return response.json()
    
    def list_orders(self, page=1, per_page=10, status=None):
        """
        List all orders with optional filtering and pagination.
        
        Args:
            page (int, optional): Page number for pagination. Defaults to 1.
            per_page (int, optional): Number of items per page. Defaults to 10.
            status (str, optional): Filter by order status. Defaults to None.
            
        Returns:
            dict: List of orders with pagination details
        """
        url = f'{self.base_url}/api/premium/orders'
        params = {'page': page, 'per_page': per_page}
        
        if status:
            params['status'] = status
            
        response = requests.get(url, headers=self.headers, params=params)
        
        # Raise exception for HTTP errors
        response.raise_for_status()
        
        # Return the orders
        return response.json()


# Example usage
if __name__ == '__main__':
    # Replace with your actual API base URL and API key
    API_BASE_URL = 'https://your-domain.com'
    API_KEY = 'your-api-key-here'
    
    # Initialize the client
    client = TelegramPremiumClient(API_BASE_URL, API_KEY)
    
    try:
        # Create a new premium order
        order = client.create_premium_order(
            telegram_username='@customer_username',
            plan_id='plan_3month',  # Replace with your actual plan ID
            crypto_currency='TRX'
        )
        
        print("Order created successfully!")
        print(f"Order ID: {order['order_id']}")
        print(f"Payment Address: {order['payment_address']}")
        print(f"Amount to Pay: {order['crypto_amount']} {order['crypto_currency']}")
        
        # Check the status of the order
        order_status = client.get_order_status(order['order_id'])
        print(f"Current Status: {order_status['status']}")
        
        # List all pending orders (optional example)
        pending_orders = client.list_orders(status='AWAITING_PAYMENT')
        print(f"Total Pending Orders: {pending_orders['total']}")
        
    except requests.exceptions.HTTPError as e:
        # Handle API errors
        print(f"API Error: {e}")
        if e.response.content:
            error_data = e.response.json()
            print(f"Error Details: {error_data.get('error')}")
    
    except Exception as e:
        # Handle other errors
        print(f"Error: {e}")