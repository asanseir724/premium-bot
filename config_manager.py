import json
import os
import logging
from config import SUBSCRIPTION_PLANS, BOT_ADMINS, SUPPORT_CONTACT

logger = logging.getLogger(__name__)

# Path to save config file
CONFIG_FILE = "config_data.json"

# Default configuration
DEFAULT_CONFIG = {
    "subscription_plans": SUBSCRIPTION_PLANS,
    "bot_admins": BOT_ADMINS,
    "support_contact": SUPPORT_CONTACT
}

# In-memory configuration
_config = None

def _load_config():
    """Load configuration from file or initialize with defaults"""
    global _config
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                _config = json.load(f)
                logger.info("Configuration loaded from file")
        else:
            _config = DEFAULT_CONFIG
            _save_config()
            logger.info("Default configuration initialized")
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        _config = DEFAULT_CONFIG
        
def _save_config():
    """Save current configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(_config, f, indent=4)
        logger.info("Configuration saved to file")
    except Exception as e:
        logger.error(f"Error saving configuration: {e}")

def get_subscription_plans():
    """Get the current subscription plans"""
    if _config is None:
        _load_config()
    return _config["subscription_plans"]

def get_plan_by_id(plan_id):
    """Get a specific subscription plan by ID"""
    plans = get_subscription_plans()
    for plan in plans:
        if plan["id"] == plan_id:
            return plan
    return None

def update_subscription_plan(plan_id, name, description, price):
    """Update a subscription plan"""
    if _config is None:
        _load_config()
        
    for plan in _config["subscription_plans"]:
        if plan["id"] == plan_id:
            plan["name"] = name
            plan["description"] = description
            plan["price"] = price
            _save_config()
            logger.info(f"Updated plan: {plan_id}")
            return True
            
    return False

def add_subscription_plan(plan_id, name, description, price):
    """Add a new subscription plan"""
    if _config is None:
        _load_config()
        
    # Check if plan with same ID already exists
    for plan in _config["subscription_plans"]:
        if plan["id"] == plan_id:
            return False
            
    # Add new plan
    _config["subscription_plans"].append({
        "id": plan_id,
        "name": name,
        "description": description,
        "price": price,
        "currency": "USD"
    })
    
    _save_config()
    logger.info(f"Added new plan: {plan_id}")
    return True

def remove_subscription_plan(plan_id):
    """Remove a subscription plan"""
    if _config is None:
        _load_config()
        
    for i, plan in enumerate(_config["subscription_plans"]):
        if plan["id"] == plan_id:
            _config["subscription_plans"].pop(i)
            _save_config()
            logger.info(f"Removed plan: {plan_id}")
            return True
            
    return False

def get_bot_admins():
    """Get the list of bot admins"""
    if _config is None:
        _load_config()
    return _config["bot_admins"]

def add_bot_admin(admin_id):
    """Add a new bot admin"""
    if _config is None:
        _load_config()
        
    if admin_id not in _config["bot_admins"]:
        _config["bot_admins"].append(admin_id)
        _save_config()
        logger.info(f"Added new admin: {admin_id}")
        return True
        
    return False

def remove_bot_admin(admin_id):
    """Remove a bot admin"""
    if _config is None:
        _load_config()
        
    if admin_id in _config["bot_admins"]:
        _config["bot_admins"].remove(admin_id)
        _save_config()
        logger.info(f"Removed admin: {admin_id}")
        return True
        
    return False

def get_support_contact():
    """Get the support contact info"""
    if _config is None:
        _load_config()
    return _config["support_contact"]

def set_support_contact(contact):
    """Set the support contact info"""
    if _config is None:
        _load_config()
        
    _config["support_contact"] = contact
    _save_config()
    logger.info(f"Updated support contact: {contact}")
    return True

# Initialize configuration
_load_config()
