
from typing import Optional, List, Dict
import os
from pathlib import Path

class CustomerDetectionConfig:
    """Configuration for customer detection features"""
    
    # GeoIP Configuration
    GEOIP_ENABLED: bool = True
    GEOIP_DATABASE_PATH: Optional[str] = os.getenv("GEOIP_DATABASE_PATH", "data/GeoLite2-City.mmdb")
    GEOIP_FALLBACK_API_ENABLED: bool = True
    GEOIP_API_RATE_LIMIT: int = 1000  # requests per month
    
    # Privacy and Compliance
    PRIVACY_MODE: str = os.getenv("PRIVACY_MODE", "standard")  # minimal, standard, enhanced
    DATA_RETENTION_DAYS: int = int(os.getenv("DATA_RETENTION_DAYS", "365"))
    COOKIE_CONSENT_REQUIRED: bool = os.getenv("COOKIE_CONSENT_REQUIRED", "true").lower() == "true"
    GDPR_COMPLIANCE: bool = os.getenv("GDPR_COMPLIANCE", "true").lower() == "true"
    
    # Device Detection
    DEVICE_FINGERPRINTING_ENABLED: bool = True
    DEVICE_FINGERPRINT_TTL_DAYS: int = 30
    BROWSER_CAPABILITY_DETECTION: bool = True
    
    # Session Management
    SESSION_TIMEOUT_HOURS: int = 24
    VISITOR_TRACKING_ENABLED: bool = True
    CROSS_DEVICE_TRACKING: bool = False  # More privacy-conscious default
    
    # External APIs
    EXTERNAL_GEOLOCATION_APIS: List[str] = [
        "ip-api.com",  # Free tier: 1000/month
        "ipstack.com",  # Requires API key
        "ipgeolocation.io"  # Requires API key
    ]
    
    # Security
    ANONYMIZE_IP_ADDRESSES: bool = True  # Mask last octet for privacy
    HASH_CUSTOMER_IDENTIFIERS: bool = True
    ENCRYPT_SENSITIVE_DATA: bool = True
    
    # Performance
    GEOLOCATION_CACHE_TTL: int = 3600  # 1 hour
    DEVICE_CACHE_TTL: int = 86400  # 24 hours
    BATCH_UPDATE_INTERVAL: int = 300  # 5 minutes
    
    # Features
    AUTOMATIC_LANGUAGE_DETECTION: bool = True
    TIMEZONE_DETECTION: bool = True
    RETURNING_VISITOR_RECOGNITION: bool = True
    INTELLIGENT_ROUTING: bool = True
    
    @classmethod
    def get_privacy_level_settings(cls, privacy_mode: str) -> Dict:
        """Get privacy settings based on privacy mode"""
        settings = {
            "minimal": {
                "store_ip_addresses": False,
                "store_user_agents": False,
                "store_geolocation": False,
                "store_device_info": False,
                "session_tracking": False,
                "data_retention_days": 30
            },
            "standard": {
                "store_ip_addresses": True,
                "store_user_agents": True,
                "store_geolocation": True,
                "store_device_info": True,
                "session_tracking": True,
                "data_retention_days": 365
            },
            "enhanced": {
                "store_ip_addresses": True,
                "store_user_agents": True,
                "store_geolocation": True,
                "store_device_info": True,
                "session_tracking": True,
                "cross_session_tracking": True,
                "behavioral_analytics": True,
                "data_retention_days": 730
            }
        }
        return settings.get(privacy_mode, settings["standard"])


# Initialize configuration
detection_config = CustomerDetectionConfig()


# app/live_chat/customer_detection_utils.py

import hashlib
import ipaddress
import re
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class CustomerDetectionUtils:
    """Utility functions for customer detection"""
    
    @staticmethod
    def anonymize_ip(ip_address: str) -> str:
        """Anonymize IP address for privacy compliance"""
        try:
            ip = ipaddress.ip_address(ip_address)
            if ip.version == 4:
                # Mask last octet for IPv4
                parts = ip_address.split('.')
                return f"{'.'.join(parts[:3])}.0"
            else:
                # Mask last 80 bits for IPv6
                network = ipaddress.ip_network(f"{ip_address}/48", strict=False)
                return str(network.network_address)
        except ValueError:
            return "0.0.0.0"
    
    @staticmethod
    def hash_identifier(identifier: str, salt: str = "customer_hash_salt") -> str:
        """Create hashed customer identifier"""
        combined = f"{identifier}:{salt}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    @staticmethod
    def extract_language_from_accept_header(accept_language: str) -> Optional[str]:
        """Extract primary language from Accept-Language header"""
        if not accept_language:
            return None
        
        # Parse Accept-Language header (e.g., "en-US,en;q=0.9,es;q=0.8")
        languages = []
        for lang_item in accept_language.split(','):
            parts = lang_item.strip().split(';')
            lang = parts[0].strip()
            quality = 1.0
            
            if len(parts) > 1 and parts[1].startswith('q='):
                try:
                    quality = float(parts[1][2:])
                except ValueError:
                    quality = 1.0
            
            languages.append((lang, quality))
        
        # Sort by quality and return primary language
        languages.sort(key=lambda x: x[1], reverse=True)
        if languages:
            primary_lang = languages[0][0]
            # Return just the language code (e.g., "en" from "en-US")
            return primary_lang.split('-')[0].lower()
        
        return None
    
    @staticmethod
    def guess_timezone_from_location(country_code: str, region: str = None) -> Optional[str]:
        """Guess timezone from geographic location"""
        # Simple timezone mapping for major countries
        timezone_mapping = {
            "US": {
                "California": "America/Los_Angeles",
                "New York": "America/New_York",
                "Texas": "America/Chicago",
                "Florida": "America/New_York",
                "default": "America/New_York"
            },
            "GB": "Europe/London",
            "DE": "Europe/Berlin",
            "FR": "Europe/Paris",
            "ES": "Europe/Madrid",
            "IT": "Europe/Rome",
            "JP": "Asia/Tokyo",
            "CN": "Asia/Shanghai",
            "AU": "Australia/Sydney",
            "CA": "America/Toronto",
            "BR": "America/Sao_Paulo",
            "IN": "Asia/Kolkata",
            "RU": "Europe/Moscow"
        }
        
        if country_code in timezone_mapping:
            country_timezones = timezone_mapping[country_code]
            if isinstance(country_timezones, dict):
                return country_timezones.get(region, country_timezones.get("default"))
            else:
                return country_timezones
        
        return None
    
    @staticmethod
    def detect_bot_traffic(user_agent: str, ip_address: str) -> bool:
        """Detect if traffic is from bots/crawlers"""
        if not user_agent:
            return True
        
        bot_indicators = [
            'bot', 'crawler', 'spider', 'scraper', 'wget', 'curl',
            'python-requests', 'urllib', 'httpx', 'axios',
            'googlebot', 'bingbot', 'slurp', 'facebookexternalhit'
        ]
        
        user_agent_lower = user_agent.lower()
        for indicator in bot_indicators:
            if indicator in user_agent_lower:
                return True
        
        # Check for suspicious patterns
        if len(user_agent) < 10 or len(user_agent) > 1000:
            return True
        
        # Check for common datacenter IP ranges (simplified)
        try:
            ip = ipaddress.ip_address(ip_address)
            # This is a simplified check - in production, use a proper datacenter IP list
            if ip.is_private or ip.is_loopback:
                return False
        except ValueError:
            return True
        
        return False
    
    @staticmethod
    def calculate_customer_risk_score(customer_data: Dict[str, Any]) -> float:
        """Calculate risk score for customer (for fraud detection)"""
        risk_score = 0.0
        
        # Check for suspicious patterns
        if customer_data.get("device_info", {}).get("is_bot"):
            risk_score += 0.8
        
        # Multiple rapid conversations
        if customer_data.get("visitor_history", {}).get("conversation_outcomes", {}).get("abandoned", 0) > 3:
            risk_score += 0.3
        
        # Unusual geographic patterns
        geolocation = customer_data.get("geolocation", {})
        if geolocation.get("country") in ["Unknown", None]:
            risk_score += 0.2
        
        # Device fingerprint changes rapidly
        device_info = customer_data.get("device_info", {})
        if not device_info.get("device_fingerprint"):
            risk_score += 0.1
        
        return min(risk_score, 1.0)
    
    @staticmethod
    def generate_session_id() -> str:
        """Generate unique session ID"""
        import uuid
        return f"sess_{uuid.uuid4().hex[:16]}"
    
    @staticmethod
    def is_valid_timezone(timezone_str: str) -> bool:
        """Validate timezone string"""
        try:
            import zoneinfo
            zoneinfo.ZoneInfo(timezone_str)
            return True
        except:
            try:
                import pytz
                pytz.timezone(timezone_str)
                return True
            except:
                return False
    
    @staticmethod
    def normalize_country_name(country: str) -> str:
        """Normalize country names for consistency"""
        if not country:
            return "Unknown"
        
        # Common normalizations
        normalizations = {
            "United States": "US",
            "United Kingdom": "UK", 
            "Great Britain": "UK",
            "Deutschland": "Germany",
            "España": "Spain",
            "França": "France"
        }
        
        return normalizations.get(country, country.title())
    
    @staticmethod
    def get_device_category(device_info: Dict) -> str:
        """Categorize device for analytics"""
        if device_info.get("is_mobile"):
            return "Mobile"
        elif device_info.get("is_tablet"):
            return "Tablet"
        elif device_info.get("device_type") == "desktop":
            return "Desktop"
        else:
            return "Unknown"
    
    @staticmethod
    def should_collect_data(privacy_preferences: Dict, data_type: str) -> bool:
        """Check if data collection is permitted based on privacy preferences"""
        if not privacy_preferences:
            return True  # Default to collecting if no preferences set
        
        consent_mapping = {
            "geolocation": "geolocation_consent",
            "device_info": "device_tracking_consent", 
            "behavioral": "behavioral_tracking_consent",
            "analytics": "analytics_consent"
        }
        
        consent_key = consent_mapping.get(data_type, "general_consent")
        return privacy_preferences.get(consent_key, True)


# app/live_chat/customer_detection_middleware.py

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging

logger = logging.getLogger(__name__)

class CustomerDetectionMiddleware(BaseHTTPMiddleware):
    """Middleware for automatic customer detection and tracking"""
    
    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
    
    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)
        
        start_time = time.time()
        
        # Add customer detection context to request
        request.state.customer_detection = {
            "start_time": start_time,
            "ip_address": self._get_client_ip(request),
            "user_agent": request.headers.get("user-agent", ""),
            "accept_language": request.headers.get("accept-language", ""),
            "referer": request.headers.get("referer", ""),
            "request_id": f"req_{int(start_time)}_{hash(request.url.path) % 10000}"
        }
        
        # Process request
        response = await call_next(request)
        
        # Add customer detection headers to response
        if hasattr(request.state, "customer_detection"):
            processing_time = time.time() - start_time
            response.headers["X-Detection-Time"] = f"{processing_time:.3f}s"
            response.headers["X-Request-ID"] = request.state.customer_detection["request_id"]
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP with proxy support"""
        # Check for forwarded IP headers
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        return getattr(request.client, "host", "127.0.0.1")


# Usage in main.py:
# app.add_middleware(CustomerDetectionMiddleware, enabled=True)