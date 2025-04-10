import os
import requests
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class NowPayments:
    """
    NowPayments API client for handling cryptocurrency payments
    """
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("NOWPAYMENTS_API_KEY")
        self.base_url = "https://api.nowpayments.io/v1"
        self.headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
    def _make_request(self, method, endpoint, data=None):
        """
        Make a request to the NowPayments API
        """
        url = f"{self.base_url}/{endpoint}"
        try:
            if method.lower() == "get":
                response = requests.get(url, headers=self.headers)
            elif method.lower() == "post":
                response = requests.post(url, headers=self.headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making {method} request to {endpoint}: {e}")
            return None
            
    def get_status(self):
        """
        Check the API status
        """
        return self._make_request("get", "status")
        
    def get_currencies(self):
        """
        Get list of available currencies
        """
        return self._make_request("get", "currencies")
        
    def get_available_currencies(self):
        """
        Get list of available cryptocurrencies for payments
        """
        return self._make_request("get", "currencies/list")
        
    def create_payment(self, price, currency="USD", pay_currency="TRX", order_id=None, order_description=None):
        """
        Create a payment
        """
        data = {
            "price_amount": price,
            "price_currency": currency,
            "pay_currency": pay_currency,
        }
        
        if order_id:
            data["order_id"] = order_id
            
        if order_description:
            data["order_description"] = order_description
            
        return self._make_request("post", "payment", data)
        
    def get_payment_status(self, payment_id):
        """
        Get the status of a payment
        """
        return self._make_request("get", f"payment/{payment_id}")
        
    def create_invoice(self, price, currency="USD", order_id=None, order_description=None, success_url=None, cancel_url=None):
        """
        Create an invoice for payment
        """
        data = {
            "price_amount": price,
            "price_currency": currency,
        }
        
        if order_id:
            data["order_id"] = order_id
            
        if order_description:
            data["order_description"] = order_description
            
        if success_url:
            data["success_url"] = success_url
            
        if cancel_url:
            data["cancel_url"] = cancel_url
            
        return self._make_request("post", "invoice", data)
        
    def get_minimum_payment_amount(self, currency="TRX"):
        """
        Get the minimum payment amount for a currency
        """
        return self._make_request("get", f"min-amount/{currency}")
        
    def verify_ipn_callback(self, ipn_data):
        """
        Verify if an IPN (Instant Payment Notification) callback is valid
        """
        # In a real implementation, you would verify the authenticity of the IPN data
        # based on NowPayments' documentation
        
        required_fields = ["payment_id", "payment_status", "pay_address", "price_amount", "price_currency"]
        
        # Check if all required fields are present
        for field in required_fields:
            if field not in ipn_data:
                logger.warning(f"Missing required field in IPN data: {field}")
                return False
                
        return True
