# app/live_chat/customer_detection_service.py

import os
import logging
import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from fastapi import Request
import httpx
import asyncio
from pathlib import Path
import time
import ipaddress
import re
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware



# Import the free geolocation service
from app.live_chat.free_geolocation_service import FreeGeolocationService

from app.live_chat.models import (
    LiveChatConversation, CustomerProfile, CustomerSession, 
    CustomerDevice, CustomerPreferences
)
from app.config import settings

logger = logging.getLogger(__name__)

class CustomerDetectionService:
    """
    Comprehensive customer detection and profiling service
    Uses free APIs for geolocation instead of local database
    """
    
    def __init__(self, db: Session):
        self.db = db
        # Use free geolocation service instead of local GeoIP database
        self.geolocation_service = FreeGeolocationService()
        self.session_timeout_hours = 24
        self.device_fingerprint_ttl_days = 30
    
    async def detect_customer(self, request: Request, tenant_id: int, 
                            customer_identifier: Optional[str] = None) -> Dict[str, Any]:
        """
        Main customer detection method
        Returns comprehensive customer profile with geolocation, device info, and history
        """
        try:
            # Extract request information
            request_info = self._extract_request_info(request)
            
            # Generate or use customer identifier
            if not customer_identifier:
                customer_identifier = self._generate_customer_identifier(request_info)
            
            # Get or create customer profile
            customer_profile = await self._get_or_create_customer_profile(
                tenant_id, customer_identifier, request_info
            )
            
            # Detect geolocation using free APIs
            geolocation = await self._detect_geolocation(request_info['ip_address'])
            
            # Analyze device and browser
            device_info = self._analyze_device(request_info['user_agent'])
            
            # Check for returning visitor
            visitor_history = await self._get_visitor_history(
                tenant_id, customer_identifier, request_info
            )
            
            # Create or update customer session
            session_info = await self._create_customer_session(
                customer_profile.id, request_info, device_info, geolocation
            )
            
            # Get customer preferences
            preferences = await self._get_customer_preferences(customer_profile.id)
            
            # Determine routing suggestions
            routing_suggestions = await self._get_routing_suggestions(
                tenant_id, geolocation, device_info, visitor_history
            )
            
            # Compile comprehensive customer data
            customer_data = {
                "customer_profile": {
                    "id": customer_profile.id,
                    "identifier": customer_identifier,
                    "is_returning_visitor": visitor_history["is_returning"],
                    "first_seen": customer_profile.first_seen.isoformat() if customer_profile.first_seen else None,
                    "last_seen": customer_profile.last_seen.isoformat() if customer_profile.last_seen else None,
                    "total_conversations": customer_profile.total_conversations,
                    "total_sessions": customer_profile.total_sessions,
                    "customer_satisfaction_avg": customer_profile.customer_satisfaction_avg,
                    "preferred_language": customer_profile.preferred_language,
                    "time_zone": customer_profile.time_zone
                },
                "current_session": session_info,
                "geolocation": geolocation,
                "device_info": device_info,
                "visitor_history": visitor_history,
                "preferences": preferences,
                "routing_suggestions": routing_suggestions,
                "privacy_compliance": {
                    "data_collection_consent": customer_profile.data_collection_consent,
                    "marketing_consent": customer_profile.marketing_consent,
                    "last_consent_update": customer_profile.last_consent_update.isoformat() if customer_profile.last_consent_update else None
                }
            }
            
            logger.info(f"Customer detection completed for {customer_identifier}")
            return customer_data
            
        except Exception as e:
            logger.error(f"Error in customer detection: {str(e)}")
            # Return minimal fallback data
            return self._create_fallback_customer_data(customer_identifier, request)
    
    async def _detect_geolocation(self, ip_address: str) -> Dict[str, Any]:
        """Detect customer geolocation using free APIs"""
        geolocation = {
            "ip_address": ip_address,
            "country": None,
            "country_code": None,
            "region": None,
            "city": None,
            "latitude": None,
            "longitude": None,
            "timezone": None,
            "isp": None,
            "detection_method": "unknown",
            "accuracy": "unknown"
        }
        
        # Handle localhost/private IPs
        if not self._is_valid_ip(ip_address):
            geolocation.update({
                "country": "Test Location (Localhost)",
                "country_code": "US",
                "region": "Development Environment", 
                "city": "Local Testing",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "timezone": "America/New_York",
                "isp": "Local Development",
                "detection_method": "localhost_fallback",
                "accuracy": "testing"
            })
            return geolocation
        
        # Use free geolocation service directly
        try:
            geolocation_api = await self.geolocation_service.get_location(ip_address)
            if geolocation_api:
                geolocation.update(geolocation_api)
                return geolocation
        except Exception as e:
            logger.error(f"External geolocation API error: {str(e)}")
        
        # Final fallback
        geolocation.update({
            "detection_method": "failed",
            "accuracy": "none"
        })
        
        return geolocation
    
    def _extract_request_info(self, request: Request) -> Dict[str, Any]:
        """Extract comprehensive information from HTTP request"""
        try:
            # Get client IP (handle proxies and load balancers)
            client_ip = self._get_client_ip(request)
            
            # Extract headers
            user_agent = request.headers.get('user-agent', '')
            accept_language = request.headers.get('accept-language', '')
            accept_encoding = request.headers.get('accept-encoding', '')
            dnt = request.headers.get('dnt', '0')  # Do Not Track
            
            # Extract additional context
            referer = request.headers.get('referer', '')
            
            return {
                "ip_address": client_ip,
                "user_agent": user_agent,
                "accept_language": accept_language,
                "accept_encoding": accept_encoding,
                "referer": referer,
                "do_not_track": dnt == '1',
                "request_time": datetime.utcnow(),
                "headers": dict(request.headers)
            }
            
        except Exception as e:
            logger.error(f"Error extracting request info: {str(e)}")
            return {
                "ip_address": "127.0.0.1",
                "user_agent": "",
                "accept_language": "en",
                "request_time": datetime.utcnow(),
                "headers": {}
            }
    
    def _get_client_ip(self, request: Request) -> str:
        """Get real client IP handling proxies and load balancers"""
        # Check common proxy headers in order of preference
        proxy_headers = [
            'cf-connecting-ip',      # Cloudflare
            'x-real-ip',            # Nginx
            'x-forwarded-for',      # Standard proxy header
            'x-client-ip',          # Apache
            'x-cluster-client-ip',  # Cluster
            'forwarded-for',        # Alternative
            'forwarded'             # RFC 7239
        ]
        
        for header in proxy_headers:
            ip = request.headers.get(header)
            if ip:
                # Handle comma-separated IPs (take first one)
                ip = ip.split(',')[0].strip()
                if self._is_valid_ip(ip):
                    return ip
        
        # Fallback to direct client IP
        client_host = getattr(request.client, 'host', '127.0.0.1')
        return client_host if self._is_valid_ip(client_host) else '127.0.0.1'
    
    def _is_valid_ip(self, ip: str) -> bool:
        """Validate IP address format"""
        try:
            import ipaddress
            ipaddress.ip_address(ip)
            return True  # Allow both public and private IPs for testing
        except ValueError:
            return False
    
    def _generate_customer_identifier(self, request_info: Dict) -> str:
        """Generate anonymous customer identifier"""
        # Create hash from IP + User Agent + Date (for privacy)
        identifier_string = f"{request_info['ip_address']}:{request_info['user_agent']}:{datetime.utcnow().date()}"
        return hashlib.sha256(identifier_string.encode()).hexdigest()[:16]
    
    def _analyze_device(self, user_agent: str) -> Dict[str, Any]:
        """Comprehensive device and browser analysis with better error handling"""
        try:
            logger.debug(f"🔍 Analyzing user agent: '{user_agent}'")
            
            # Try importing user_agents with fallback
            try:
                from user_agents import parse as parse_user_agent
                parsed_ua = parse_user_agent(user_agent)
                logger.debug(f"✅ User agent parsed successfully")
            except ImportError:
                logger.warning("⚠️ user_agents library not installed, using fallback")
                return self._fallback_device_analysis(user_agent)
            except Exception as e:
                logger.warning(f"⚠️ Error parsing user agent: {str(e)}, using fallback")
                return self._fallback_device_analysis(user_agent)
            
            # Determine device type
            device_type = "desktop"
            if parsed_ua.is_mobile:
                device_type = "mobile"
            elif parsed_ua.is_tablet:
                device_type = "tablet"
            elif parsed_ua.is_pc:
                device_type = "desktop"
            
            # Extract browser capabilities
            capabilities = self._analyze_browser_capabilities(user_agent)
            
            # Generate device fingerprint (for returning visitor detection)
            device_fingerprint = self._generate_device_fingerprint(user_agent)
            
            result = {
                "device_type": device_type,
                "browser": {
                    "name": parsed_ua.browser.family or "Unknown",
                    "version": parsed_ua.browser.version_string or "Unknown",
                    "engine": getattr(parsed_ua.browser, 'engine', 'unknown')
                },
                "operating_system": {
                    "name": parsed_ua.os.family or "Unknown",
                    "version": parsed_ua.os.version_string or "Unknown"
                },
                "device": {
                    "brand": getattr(parsed_ua.device, 'brand', None),
                    "model": getattr(parsed_ua.device, 'model', None),
                    "family": getattr(parsed_ua.device, 'family', 'Other')
                },
                "capabilities": capabilities,
                "is_mobile": parsed_ua.is_mobile,
                "is_tablet": parsed_ua.is_tablet,
                "is_bot": parsed_ua.is_bot,
                "device_fingerprint": device_fingerprint,
                "user_agent": user_agent
            }
            
            logger.debug(f"✅ Device analysis completed: {device_type}")
            return result
            
        except Exception as e:
            logger.error(f"🚨 Device analysis error: {str(e)}")
            return self._fallback_device_analysis(user_agent)

    def _fallback_device_analysis(self, user_agent: str) -> Dict[str, Any]:
        """Fallback device analysis when user_agents library fails"""
        logger.debug(f"Using fallback device analysis for: '{user_agent}'")
        
        # Simple regex-based detection
        is_mobile = any(keyword in user_agent.lower() for keyword in [
            'mobile', 'android', 'iphone', 'ipad', 'blackberry', 'windows phone'
        ])
        
        is_tablet = any(keyword in user_agent.lower() for keyword in [
            'ipad', 'tablet', 'kindle'
        ])
        
        # Simple browser detection
        browser_name = "Unknown"
        browser_version = "Unknown"
        
        if 'chrome' in user_agent.lower():
            browser_name = "Chrome"
            import re
            version_match = re.search(r'chrome/(\d+\.\d+)', user_agent.lower())
            if version_match:
                browser_version = version_match.group(1)
        elif 'firefox' in user_agent.lower():
            browser_name = "Firefox"
        elif 'safari' in user_agent.lower() and 'chrome' not in user_agent.lower():
            browser_name = "Safari"
        elif 'edge' in user_agent.lower():
            browser_name = "Edge"
        
        # Simple OS detection
        os_name = "Unknown"
        if 'windows' in user_agent.lower():
            os_name = "Windows"
        elif 'mac os' in user_agent.lower() or 'macos' in user_agent.lower():
            os_name = "macOS"
        elif 'linux' in user_agent.lower():
            os_name = "Linux"
        elif 'android' in user_agent.lower():
            os_name = "Android"
        elif 'ios' in user_agent.lower() or 'iphone' in user_agent.lower():
            os_name = "iOS"
        
        device_type = "mobile" if is_mobile else "tablet" if is_tablet else "desktop"
        
        return {
            "device_type": device_type,
            "browser": {
                "name": browser_name,
                "version": browser_version,
                "engine": "unknown"
            },
            "operating_system": {
                "name": os_name,
                "version": "unknown"
            },
            "device": {
                "brand": None,
                "model": None,
                "family": "Other"
            },
            "capabilities": self._analyze_browser_capabilities(user_agent),
            "is_mobile": is_mobile,
            "is_tablet": is_tablet,
            "is_bot": self._detect_bot_traffic(user_agent, ""),
            "device_fingerprint": self._generate_device_fingerprint(user_agent),
            "user_agent": user_agent
        }
    
    def _analyze_browser_capabilities(self, user_agent: str) -> Dict[str, bool]:
        """Analyze browser capabilities for compatibility"""
        capabilities = {
            "supports_websockets": True,  # Assume modern browser
            "supports_webrtc": True,
            "supports_file_upload": True,
            "supports_notifications": True,
            "supports_geolocation": True,
            "supports_local_storage": True
        }
        
        # Check for older browsers with limited capabilities
        ua_lower = user_agent.lower()
        
        if 'msie' in ua_lower or 'trident' in ua_lower:
            # Internet Explorer
            capabilities.update({
                "supports_websockets": "msie 10" in ua_lower or "rv:11" in ua_lower,
                "supports_webrtc": False,
                "supports_notifications": False
            })
        
        return capabilities
    
    def _generate_device_fingerprint(self, user_agent: str) -> str:
        """Generate device fingerprint for returning visitor detection"""
        # Create a stable but privacy-conscious fingerprint
        fingerprint_data = f"{user_agent}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
    
    def _detect_bot_traffic(self, user_agent: str, ip_address: str) -> bool:
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
        
        return False
    
    # ... rest of the methods remain the same
    async def _get_visitor_history(self, tenant_id: int, customer_identifier: str, 
                                 request_info: Dict) -> Dict[str, Any]:
        """Get comprehensive visitor history and previous conversations"""
        try:
            # Check for existing customer profile
            existing_profile = self.db.query(CustomerProfile).filter(
                and_(
                    CustomerProfile.tenant_id == tenant_id,
                    CustomerProfile.customer_identifier == customer_identifier
                )
            ).first()
            
            history = {
                "is_returning": False,
                "previous_conversations": [],
                "last_conversation": None,
                "total_visits": 0,
                "first_visit": None,
                "last_visit": None,
                "preferred_agents": [],
                "conversation_outcomes": {
                    "resolved": 0,
                    "unresolved": 0,
                    "abandoned": 0
                }
            }
            
            if existing_profile:
                history["is_returning"] = True
                history["first_visit"] = existing_profile.first_seen.isoformat()
                history["last_visit"] = existing_profile.last_seen.isoformat()
                history["total_visits"] = existing_profile.total_sessions
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting visitor history: {str(e)}")
            return {"is_returning": False, "error": str(e)}
    
    async def _get_or_create_customer_profile(self, tenant_id: int, customer_identifier: str, request_info: Dict) -> 'CustomerProfile':
        """Get existing customer profile or create new one"""
        try:
            from app.live_chat.models import CustomerProfile
            
            # Try to find existing profile
            customer_profile = self.db.query(CustomerProfile).filter(
                and_(
                    CustomerProfile.tenant_id == tenant_id,
                    CustomerProfile.customer_identifier == customer_identifier
                )
            ).first()
            
            if customer_profile:
                # Update last seen
                customer_profile.last_seen = datetime.utcnow()
                customer_profile.total_sessions += 1
                self.db.commit()
                return customer_profile
            
            # Create new profile
            customer_profile = CustomerProfile(
                tenant_id=tenant_id,
                customer_identifier=customer_identifier,
                first_seen=datetime.utcnow(),
                last_seen=datetime.utcnow(),
                total_conversations=0,
                total_sessions=1,
                data_collection_consent=True,
                marketing_consent=False
            )
            
            self.db.add(customer_profile)
            self.db.commit()
            self.db.refresh(customer_profile)
            
            logger.info(f"Created new customer profile for {customer_identifier}")
            return customer_profile
            
        except Exception as e:
            logger.error(f"Error creating customer profile: {str(e)}")
            from app.live_chat.models import CustomerProfile
            return CustomerProfile(
                tenant_id=tenant_id,
                customer_identifier=customer_identifier,
                first_seen=datetime.utcnow(),
                last_seen=datetime.utcnow(),
                total_conversations=0,
                total_sessions=0
            )
        
    async def _create_customer_session(self, customer_profile_id: int, request_info: Dict, 
                                    device_info: Dict, geolocation: Dict) -> Dict:
        """Create customer session record"""
        try:
            from app.live_chat.models import CustomerSession
            
            session = CustomerSession(
                customer_profile_id=customer_profile_id,
                session_id=f"sess_{uuid.uuid4().hex[:16]}",
                started_at=datetime.utcnow(),
                ip_address=request_info.get('ip_address'),
                user_agent=request_info.get('user_agent'),
                device_fingerprint=device_info.get('device_fingerprint'),
                country=geolocation.get('country'),
                region=geolocation.get('region'),
                city=geolocation.get('city'),
                page_views=1,
                conversations_started=0
            )
            
            self.db.add(session)
            self.db.commit()
            
            return {
                "session_id": session.session_id,
                "started_at": session.started_at.isoformat(),
                "ip_address": session.ip_address,
                "country": session.country,
                "city": session.city
            }
            
        except Exception as e:
            logger.error(f"Error creating customer session: {str(e)}")
            return {
                "session_id": f"temp_{uuid.uuid4().hex[:8]}",
                "started_at": datetime.utcnow().isoformat(),
                "error": "session_creation_failed"
            }

    async def _get_customer_preferences(self, customer_profile_id: int) -> Dict:
        """Get customer preferences"""
        try:
            from app.live_chat.models import CustomerPreferences
            
            preferences = self.db.query(CustomerPreferences).filter(
                CustomerPreferences.customer_profile_id == customer_profile_id
            ).first()
            
            if preferences:
                return {
                    "preferred_language": preferences.preferred_language,
                    "communication_style": preferences.preferred_communication_style,
                    "accessibility_required": preferences.requires_accessibility_features,
                    "email_notifications": preferences.email_notifications,
                    "data_retention": preferences.data_retention_preference
                }
            
            return {
                "preferred_language": "en",
                "communication_style": "standard",
                "accessibility_required": False,
                "email_notifications": False,
                "data_retention": "standard"
            }
            
        except Exception as e:
            logger.error(f"Error getting customer preferences: {str(e)}")
            return {}

    async def _get_routing_suggestions(self, tenant_id: int, geolocation: Dict,
                                     device_info: Dict, visitor_history: Dict) -> Dict[str, Any]:
        """Generate intelligent agent routing suggestions"""
        try:
            suggestions = {
                "recommended_agents": [],
                "routing_criteria": [],
                "priority_score": 1.0,
                "special_considerations": []
            }
            
            # Geographic routing
            if geolocation.get("country"):
                suggestions["routing_criteria"].append(f"Geographic: {geolocation['country']}")
            
            # Device-specific routing
            if device_info.get("device_type") == "mobile":
                suggestions["special_considerations"].append("Mobile user - prefer agents with mobile support expertise")
            
            # Add fallback recommendation
            suggestions["recommended_agents"].append({
                "agent_id": None,
                "agent_name": "Next Available Agent",
                "reason": "Auto-assignment to next available agent",
                "priority": 0.5
            })
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error generating routing suggestions: {str(e)}")
            return {
                "recommended_agents": [],
                "routing_criteria": ["Error generating suggestions"],
                "priority_score": 1.0,
                "special_considerations": ["System error - use default routing"],
                "error": str(e)
            }
            
    def _create_fallback_customer_data(self, customer_identifier: Optional[str], 
                                     request: Request) -> Dict[str, Any]:
        """Create minimal fallback customer data when detection fails"""
        return {
            "customer_profile": {
                "identifier": customer_identifier or "unknown",
                "is_returning_visitor": False,
                "error": "Detection failed"
            },
            "current_session": {"error": "Session creation failed"},
            "geolocation": {"detection_method": "failed"},
            "device_info": {"device_type": "unknown"},
            "visitor_history": {"is_returning": False},
            "preferences": {},
            "routing_suggestions": {"error": "Routing unavailable"},
            "privacy_compliance": {"data_collection_consent": None}
        }
    


class CustomerDetectionConfig:
    """Configuration for customer detection features"""
    
    # GeoIP Configuration - Updated to prefer free APIs
    GEOIP_ENABLED: bool = True
    GEOIP_METHOD: str = os.getenv("GEOIP_METHOD", "free_api")  # "free_api" or "local_database"
    GEOIP_DATABASE_PATH: Optional[str] = os.getenv("GEOIP_DATABASE_PATH", "data/GeoLite2-City.mmdb")
    GEOIP_FALLBACK_API_ENABLED: bool = True
    GEOIP_API_RATE_LIMIT: int = 1000  # requests per month
    
    # Free API Configuration
    FREE_GEOLOCATION_ENABLED: bool = True
    FREE_GEOLOCATION_CACHE_TTL: int = 86400  # 24 hours
    FREE_GEOLOCATION_TIMEOUT: int = 5  # 5 seconds timeout
    
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
    
    # External APIs - Updated with working free APIs
    EXTERNAL_GEOLOCATION_APIS: List[str] = [
        "ip-api.com",        # Free tier: 45 requests/minute, 1000/month
        "ipinfo.io",         # Free tier: 50k requests/month
        "freeipapi.com"      # Free tier: 60 requests/minute, 1000/month
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
        
        return False
    
    @staticmethod
    def calculate_customer_risk_score(customer_data: Dict[str, any]) -> float:
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


# Initialize configuration
detection_config = CustomerDetectionConfig()