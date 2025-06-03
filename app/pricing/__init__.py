# app/pricing/__init__.py
"""
Minimal pricing module init to fix import errors
Replace your current __init__.py with this temporarily
"""

# Import only what's needed to fix the immediate import error
try:
    from .integration_helpers import (
        check_message_limit_dependency,
        track_message_sent,
        check_integration_limit_dependency,
        check_feature_access_dependency,
        track_integration_added,
        track_integration_removed,
        get_tenant_usage_summary,
        check_and_warn_usage_limits
    )
except ImportError as e:
    print(f"Warning: Could not import pricing helpers: {e}")
    # Create placeholder functions if import fails
    def check_message_limit_dependency(*args, **kwargs):
        pass
    def track_message_sent(*args, **kwargs):
        return True
    def check_integration_limit_dependency(*args, **kwargs):
        pass
    def check_feature_access_dependency(*args, **kwargs):
        pass
    def track_integration_added(*args, **kwargs):
        return True
    def track_integration_removed(*args, **kwargs):
        return True
    def get_tenant_usage_summary(*args, **kwargs):
        return {}
    def check_and_warn_usage_limits(*args, **kwargs):
        return []

__all__ = [
    "check_message_limit_dependency",
    "track_message_sent", 
    "check_integration_limit_dependency",
    "check_feature_access_dependency",
    "track_integration_added",
    "track_integration_removed",
    "get_tenant_usage_summary",
    "check_and_warn_usage_limits"
]