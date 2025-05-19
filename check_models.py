#!/usr/bin/env python3
"""
Script to check model relationships
"""
import os
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_models():
    """Check model relationships"""
    from app.database import engine, Base
    
    # Import models
    from app.tenants.models import Tenant
    from app.auth.models import TenantCredentials
    
    # Check Tenant model
    logger.info("Tenant model attributes:")
    for attr in dir(Tenant):
        if not attr.startswith('_'):
            logger.info(f"  - {attr}")
    
    # Check TenantCredentials model
    logger.info("\nTenantCredentials model attributes:")
    for attr in dir(TenantCredentials):
        if not attr.startswith('_'):
            logger.info(f"  - {attr}")
    
    logger.info("\nModel check complete")

if __name__ == "__main__":
    check_models()