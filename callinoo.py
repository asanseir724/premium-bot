import os
import json
import logging
import requests
import time
from typing import Dict, Any, Optional, List, Union

# Configure logging
logger = logging.getLogger(__name__)

class CallinooAPI:
    """
    Callinoo API client for integrating with virtual phone numbers and Telegram Premium services.
    """
    
    BASE_URL = "https://api.ozvinoo.xyz/web"
    
    def __init__(self, token: str = None):
        """
        Initialize the Callinoo API client.
        
        Args:
            token (str): API token for authentication. If not provided, will try to get from environment.
        """
        self.token = token or os.environ.get("CALLINOO_API_TOKEN")
        if not self.token:
            logger.warning("No Callinoo API token provided.")
        
        self.session = requests.Session()
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None) -> Dict:
        """
        Make a request to the Callinoo API.
        
        Args:
            method (str): HTTP method to use (get, post, etc.)
            endpoint (str): API endpoint to request
            params (Dict, optional): Query parameters for GET requests
            data (Dict, optional): JSON data for POST requests
        
        Returns:
            Dict: The JSON response from the API
        """
        url = f"{self.BASE_URL}/{self.token}/{endpoint}"
        
        try:
            if method.lower() == 'get':
                response = self.session.get(url, params=params)
            elif method.lower() == 'post':
                response = self.session.post(url, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request error: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"API response: {e.response.text}")
            raise
    
    # Balance related methods
    def get_balance(self) -> Dict:
        """
        Get the current balance of the user account.
        
        Returns:
            Dict: Account balance information
        """
        return self._make_request('get', 'getBalance')
    
    # Service related methods
    def get_services(self) -> List[Dict]:
        """
        Get list of available services.
        
        Returns:
            List[Dict]: Available services
        """
        return self._make_request('get', 'applications')
    
    def get_prices(self, service_id: Optional[int] = None, country: Optional[str] = None) -> Dict:
        """
        Get prices for services.
        
        Args:
            service_id (int, optional): ID of the service to check prices for
            country (str, optional): Country to check prices for
        
        Returns:
            Dict: Service pricing information
        """
        endpoint = "getPrices"
        params = {}
        
        if service_id:
            params['service_id'] = service_id
        if country:
            params['country'] = country
            
        return self._make_request('get', endpoint, params=params)
    
    # Virtual number methods
    def get_number(self, service_id: int, country: Optional[str] = None) -> Dict:
        """
        Get a virtual phone number.
        
        Args:
            service_id (int): ID of the service to get a number for
            country (str, optional): Specific country to get a number from
        
        Returns:
            Dict: Virtual number information
        """
        endpoint = f"getNumber/{service_id}"
        if country:
            endpoint += f"/{country}"
            
        return self._make_request('get', endpoint)
    
    def get_code(self, request_id: str) -> Dict:
        """
        Get the verification code for a previously requested number.
        
        Args:
            request_id (str): The request ID from the get_number call
        
        Returns:
            Dict: Verification code information
        """
        endpoint = f"getCode/{request_id}"
        return self._make_request('get', endpoint)
    
    def logout(self, request_id: str) -> Dict:
        """
        Log out the bot from the user account (ends the virtual number session).
        
        Args:
            request_id (str): The request ID from the get_number call
        
        Returns:
            Dict: Logout status
        """
        endpoint = f"logout/{request_id}"
        return self._make_request('get', endpoint)
    
    # Telegram Premium methods
    def telegram_premium_create(self, telegram_username: str, period: str = 'monthly', quantity: int = 1) -> Dict:
        """
        Create a Telegram Premium subscription order.
        
        Args:
            telegram_username (str): Telegram username to activate premium for
            period (str, optional): Subscription period - 'monthly', 'annual', etc.
            quantity (int, optional): Number of subscriptions to purchase
        
        Returns:
            Dict: Order information
        """
        endpoint = "telegram/premium/create"
        data = {
            "telegram_username": telegram_username.lstrip('@'),
            "period": period,
            "quantity": quantity
        }
        
        return self._make_request('post', endpoint, data=data)
    
    def telegram_premium_check(self, order_id: str) -> Dict:
        """
        Check the status of a Telegram Premium subscription order.
        
        Args:
            order_id (str): The order ID returned from telegram_premium_create
        
        Returns:
            Dict: Order status information
        """
        endpoint = f"telegram/premium/check/{order_id}"
        return self._make_request('get', endpoint)

    def wait_for_telegram_premium_activation(self, order_id: str, max_attempts: int = 10, delay_seconds: int = 5) -> Dict:
        """
        Wait and repeatedly check for a Telegram Premium subscription to be activated.
        
        Args:
            order_id (str): The order ID returned from telegram_premium_create
            max_attempts (int, optional): Maximum number of status check attempts
            delay_seconds (int, optional): Delay between status checks
            
        Returns:
            Dict: Final order status
        """
        attempts = 0
        
        while attempts < max_attempts:
            attempts += 1
            
            try:
                status = self.telegram_premium_check(order_id)
                
                # Check if activation is complete
                if status.get('status') == 'completed':
                    logger.info(f"Telegram Premium activated successfully for order {order_id}")
                    return status
                
                # Check if activation failed
                if status.get('status') in ['failed', 'cancelled', 'error']:
                    logger.error(f"Telegram Premium activation failed for order {order_id}: {status}")
                    return status
                
                # Still processing
                logger.info(f"Telegram Premium activation in progress for order {order_id}. Attempt {attempts}/{max_attempts}")
                
                # Wait before next check
                time.sleep(delay_seconds)
                
            except Exception as e:
                logger.error(f"Error checking Telegram Premium status: {e}")
                time.sleep(delay_seconds)
        
        logger.warning(f"Reached maximum attempts ({max_attempts}) for order {order_id}")
        return {"status": "timeout", "message": "Maximum check attempts reached"}