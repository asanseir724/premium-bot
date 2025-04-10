"""
Telegram Premium Service Handler

This module is responsible for handling the Telegram Premium subscription services
through different providers like Callinoo API.
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

import config_manager
from callinoo import CallinooAPI

# Configure logging
logger = logging.getLogger(__name__)

class TelegramPremiumService:
    """Service for handling Telegram Premium subscriptions"""
    
    @staticmethod
    def is_callinoo_enabled() -> bool:
        """Check if Callinoo integration is enabled for Telegram Premium"""
        return config_manager.get_config_value('use_callinoo_for_premium', False)
    
    @staticmethod
    def get_callinoo_client() -> Optional[CallinooAPI]:
        """Get a configured Callinoo API client if enabled"""
        if not TelegramPremiumService.is_callinoo_enabled():
            return None
            
        callinoo_token = config_manager.get_config_value('callinoo_token', '')
        if not callinoo_token:
            logger.warning("Callinoo integration is enabled but no token is configured")
            return None
            
        return CallinooAPI(token=callinoo_token)
    
    @staticmethod
    def create_premium_subscription(telegram_username: str, period: str = 'monthly') -> Dict[str, Any]:
        """
        Create a new Telegram Premium subscription using the configured provider.
        
        Args:
            telegram_username (str): The Telegram username to activate premium for
            period (str): The subscription period ('monthly' or 'annual')
            
        Returns:
            Dict: Result of the subscription attempt with status and details
        """
        # Remove @ symbol if present in the username
        telegram_username = telegram_username.lstrip('@')
        
        # Check if we're using Callinoo for Premium
        if TelegramPremiumService.is_callinoo_enabled():
            try:
                client = TelegramPremiumService.get_callinoo_client()
                if not client:
                    return {
                        "success": False,
                        "message": "Callinoo client configuration error",
                        "provider": "callinoo"
                    }
                
                # Make the API call to create a subscription
                result = client.telegram_premium_create(
                    telegram_username=telegram_username,
                    period=period,
                    quantity=1  # Default to 1 subscription
                )
                
                # Check the result
                if 'error' in result:
                    return {
                        "success": False,
                        "message": result.get('error', 'Unknown error'),
                        "provider": "callinoo",
                        "raw_response": result
                    }
                
                # Success case
                return {
                    "success": True,
                    "message": "Premium subscription created",
                    "provider": "callinoo",
                    "order_id": result.get('order_id'),
                    "activation_link": result.get('activation_link'),
                    "status": result.get('status', 'pending'),
                    "raw_response": result
                }
                
            except Exception as e:
                logger.error(f"Error creating Telegram Premium with Callinoo: {str(e)}")
                return {
                    "success": False,
                    "message": f"API error: {str(e)}",
                    "provider": "callinoo"
                }
        
        # If no provider is enabled or we reach here for any reason
        return {
            "success": False,
            "message": "No premium subscription provider enabled",
            "provider": "none"
        }
    
    @staticmethod
    def check_subscription_status(order_id: str, provider: str = 'callinoo') -> Dict[str, Any]:
        """
        Check the status of a Telegram Premium subscription.
        
        Args:
            order_id (str): The order ID to check
            provider (str): The provider used for this subscription
            
        Returns:
            Dict: Current status of the subscription
        """
        if provider == 'callinoo' and TelegramPremiumService.is_callinoo_enabled():
            try:
                client = TelegramPremiumService.get_callinoo_client()
                if not client:
                    return {
                        "success": False,
                        "message": "Callinoo client configuration error",
                        "provider": "callinoo"
                    }
                
                # Check the status
                result = client.telegram_premium_check(order_id)
                
                # Check for errors
                if 'error' in result:
                    return {
                        "success": False,
                        "message": result.get('error', 'Unknown error'),
                        "provider": "callinoo",
                        "raw_response": result
                    }
                
                # Success case
                return {
                    "success": True,
                    "status": result.get('status', 'unknown'),
                    "provider": "callinoo",
                    "activation_link": result.get('activation_link'),
                    "raw_response": result
                }
                
            except Exception as e:
                logger.error(f"Error checking Telegram Premium status with Callinoo: {str(e)}")
                return {
                    "success": False,
                    "message": f"API error: {str(e)}",
                    "provider": "callinoo"
                }
        
        # If no provider matches or we reach here for any reason
        return {
            "success": False,
            "message": f"Provider '{provider}' not supported or enabled",
            "provider": provider
        }
    
    @staticmethod
    def wait_for_subscription_activation(order_id: str, provider: str = 'callinoo', 
                                        max_attempts: int = 10, delay_seconds: int = 5) -> Dict[str, Any]:
        """
        Wait for a subscription to be activated, periodically checking status.
        
        Args:
            order_id (str): The order ID to check
            provider (str): The provider used for this subscription
            max_attempts (int): Maximum number of status check attempts
            delay_seconds (int): Delay between status checks
            
        Returns:
            Dict: Final status of the subscription
        """
        if provider == 'callinoo' and TelegramPremiumService.is_callinoo_enabled():
            try:
                client = TelegramPremiumService.get_callinoo_client()
                if not client:
                    return {
                        "success": False,
                        "message": "Callinoo client configuration error",
                        "provider": "callinoo"
                    }
                
                # Use the wait_for_activation method
                result = client.wait_for_telegram_premium_activation(
                    order_id=order_id,
                    max_attempts=max_attempts,
                    delay_seconds=delay_seconds
                )
                
                # Check for errors
                if 'error' in result:
                    return {
                        "success": False,
                        "message": result.get('error', 'Unknown error'),
                        "provider": "callinoo",
                        "raw_response": result
                    }
                
                # Determine success based on status
                success = result.get('status') == 'completed'
                
                # Return standardized result
                return {
                    "success": success,
                    "status": result.get('status', 'unknown'),
                    "message": "Premium activation complete" if success else f"Premium activation failed: {result.get('status')}",
                    "provider": "callinoo",
                    "activation_link": result.get('activation_link'),
                    "raw_response": result
                }
                
            except Exception as e:
                logger.error(f"Error waiting for Telegram Premium activation: {str(e)}")
                return {
                    "success": False,
                    "message": f"API error: {str(e)}",
                    "provider": "callinoo"
                }
        
        # If no provider matches or we reach here for any reason
        return {
            "success": False,
            "message": f"Provider '{provider}' not supported or enabled",
            "provider": provider
        }