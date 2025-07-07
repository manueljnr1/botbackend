
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
from user_agents import parse as parse_user_agent
import geoip2.database
import geoip2.errors
from pathlib import Path
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
    Handles geolocation, device fingerprinting, and returning visitor recognition
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.geolocation_service = FreeGeolocationService()
        self.session_timeout_hours = 24
        self.device_fingerprint_ttl_days = 30
    
    def _initialize_geoip(self):
        """Initialize GeoIP2 database reader with error handling"""
        try:
            # Check for GeoLite2 database files
            possible_paths = [
                Path("data/GeoLite2-City.mmdb"),
                Path("/opt/geoip/GeoLite2-City.mmdb"),
                Path("./GeoLite2-City.mmdb"),
                Path(getattr(settings, 'GEOIP_DATABASE_PATH', ''))
            ]
            
            for path in possible_paths:
                if path.exists() and path.is_file():
                    logger.info(f"Loading GeoIP database from: {path}")
                    return geoip2.database.Reader(str(path))
            
            logger.warning("GeoIP database not found. Geolocation features disabled.")
            return None
            
        except Exception as e:
            logger.error(f"Failed to initialize GeoIP database: {str(e)}")
            return None
    
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
            
            # Detect geolocation
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
            return not ipaddress.ip_address(ip).is_private
        except ValueError:
            return False
    
    def _generate_customer_identifier(self, request_info: Dict) -> str:
        """Generate anonymous customer identifier"""
        # Create hash from IP + User Agent + Date (for privacy)
        identifier_string = f"{request_info['ip_address']}:{request_info['user_agent']}:{datetime.utcnow().date()}"
        return hashlib.sha256(identifier_string.encode()).hexdigest()[:16]
    
    async def _detect_geolocation(self, ip_address: str) -> Dict[str, Any]:
        """Detect customer geolocation with multiple fallback methods"""
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
        
        # Handle localhost/private IPs for testing - PROVIDE FALLBACK DATA INSTEAD OF SKIPPING
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
            return geolocation  # Return the fallback data instead of skipping
        
        # Method 1: Local GeoIP2 database (fastest, most private)
        if self.geoip_reader:
            try:
                response = self.geoip_reader.city(ip_address)
                geolocation.update({
                    "country": response.country.name,
                    "country_code": response.country.iso_code,
                    "region": response.subdivisions.most_specific.name,
                    "city": response.city.name,
                    "latitude": float(response.location.latitude) if response.location.latitude else None,
                    "longitude": float(response.location.longitude) if response.location.longitude else None,
                    "timezone": response.location.time_zone,
                    "detection_method": "geoip2_local",
                    "accuracy": "high"
                })
                return geolocation
            except geoip2.errors.AddressNotFoundError:
                logger.debug(f"IP {ip_address} not found in GeoIP database")
            except Exception as e:
                logger.error(f"GeoIP2 lookup error: {str(e)}")
        
        # Method 2: External API fallback (with rate limiting)
        try:
            geolocation_api = await self._fetch_external_geolocation(ip_address)
            if geolocation_api:
                geolocation.update(geolocation_api)
                return geolocation
        except Exception as e:
            logger.error(f"External geolocation API error: {str(e)}")
        
        # Method 3: Browser geolocation hint from accept-language
        if not geolocation["country"]:
            country_from_lang = self._guess_country_from_language(
                self.request_info.get('accept_language', '')
            )
            if country_from_lang:
                geolocation.update({
                    "country": country_from_lang,
                    "detection_method": "language_hint",
                    "accuracy": "low"
                })
        
        # Final fallback if everything fails
        if not geolocation["country"]:
            geolocation.update({
                "detection_method": "failed",
                "accuracy": "none"
            })
        
        return geolocation
    
    async def _fetch_external_geolocation(self, ip_address: str) -> Optional[Dict]:
        """Fetch geolocation from external API with rate limiting"""
        try:
            # Use ip-api.com (free tier: 1000 requests/month)
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"http://ip-api.com/json/{ip_address}?fields=status,message,country,countryCode,region,regionName,city,lat,lon,timezone,isp"
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('status') == 'success':
                        return {
                            "country": data.get('country'),
                            "country_code": data.get('countryCode'),
                            "region": data.get('regionName'),
                            "city": data.get('city'),
                            "latitude": data.get('lat'),
                            "longitude": data.get('lon'),
                            "timezone": data.get('timezone'),
                            "isp": data.get('isp'),
                            "detection_method": "external_api",
                            "accuracy": "medium"
                        }
        except Exception as e:
            logger.error(f"External geolocation API failed: {str(e)}")
        
        return None
    
    def _analyze_device(self, user_agent: str) -> Dict[str, Any]:
        """Comprehensive device and browser analysis"""
        try:
            # Add debug logging
            print(f"🔍 DEBUG: Analyzing user agent: '{user_agent}'")
            
            # Try importing user_agents
            try:
                from user_agents import parse as parse_user_agent
                parsed_ua = parse_user_agent(user_agent)
                print(f"🔍 DEBUG: Parsed UA successfully: {parsed_ua}")
            except ImportError:
                print("⚠️ user_agents library not installed, using fallback")
                return self._fallback_device_analysis(user_agent)
            except Exception as e:
                print(f"⚠️ Error parsing user agent: {str(e)}")
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
            
            print(f"🔍 DEBUG: Device analysis result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing device: {str(e)}")
            print(f"🚨 DEBUG: Device analysis error: {str(e)}")
            return self._fallback_device_analysis(user_agent)

    def _fallback_device_analysis(self, user_agent: str) -> Dict[str, Any]:
        """Fallback device analysis when user_agents library fails"""
        print(f"🔍 DEBUG: Using fallback device analysis for: '{user_agent}'")
        
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
            import re
            version_match = re.search(r'firefox/(\d+\.\d+)', user_agent.lower())
            if version_match:
                browser_version = version_match.group(1)
        elif 'safari' in user_agent.lower() and 'chrome' not in user_agent.lower():
            browser_name = "Safari"
            import re
            version_match = re.search(r'version/(\d+\.\d+)', user_agent.lower())
            if version_match:
                browser_version = version_match.group(1)
        elif 'edge' in user_agent.lower():
            browser_name = "Edge"
            import re
            version_match = re.search(r'edge/(\d+\.\d+)', user_agent.lower())
            if version_match:
                browser_version = version_match.group(1)
        
        # Simple OS detection
        os_name = "Unknown"
        if 'windows' in user_agent.lower():
            os_name = "Windows"
            if 'windows nt 10' in user_agent.lower():
                os_name = "Windows 10"
            elif 'windows nt 6.1' in user_agent.lower():
                os_name = "Windows 7"
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
        
        if 'chrome' in ua_lower:
            # Extract Chrome version for capability detection
            import re
            version_match = re.search(r'chrome/(\d+)', ua_lower)
            if version_match:
                chrome_version = int(version_match.group(1))
                capabilities.update({
                    "supports_webrtc": chrome_version >= 23,
                    "supports_notifications": chrome_version >= 22
                })
        
        return capabilities
    
    def _generate_device_fingerprint(self, user_agent: str) -> str:
        """Generate device fingerprint for returning visitor detection"""
        # Create a stable but privacy-conscious fingerprint
        fingerprint_data = f"{user_agent}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
    
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
            
            if not existing_profile:
                return history
            
            history["is_returning"] = True
            history["first_visit"] = existing_profile.first_seen.isoformat()
            history["last_visit"] = existing_profile.last_seen.isoformat()
            history["total_visits"] = existing_profile.total_sessions
            
            # Get recent conversations
            recent_conversations = self.db.query(LiveChatConversation).filter(
                and_(
                    LiveChatConversation.tenant_id == tenant_id,
                    LiveChatConversation.customer_identifier == customer_identifier
                )
            ).order_by(desc(LiveChatConversation.created_at)).limit(10).all()
            
            conversation_list = []
            for conv in recent_conversations:
                conversation_list.append({
                    "id": conv.id,
                    "created_at": conv.created_at.isoformat(),
                    "status": conv.status,
                    "resolution_status": conv.resolution_status,
                    "customer_satisfaction": conv.customer_satisfaction,
                    "agent_id": conv.assigned_agent_id,
                    "duration_minutes": conv.conversation_duration_seconds // 60 if conv.conversation_duration_seconds else None,
                    "message_count": conv.message_count
                })
            
            history["previous_conversations"] = conversation_list
            if conversation_list:
                history["last_conversation"] = conversation_list[0]
            
            # Analyze conversation outcomes
            for conv in recent_conversations:
                if conv.resolution_status == "resolved":
                    history["conversation_outcomes"]["resolved"] += 1
                elif conv.status == "abandoned":
                    history["conversation_outcomes"]["abandoned"] += 1
                else:
                    history["conversation_outcomes"]["unresolved"] += 1
            
            # Get preferred agents (most frequently assigned)
            from sqlalchemy import func
            agent_frequency = self.db.query(
                LiveChatConversation.assigned_agent_id,
                func.count(LiveChatConversation.id).label('count')
            ).filter(
                and_(
                    LiveChatConversation.tenant_id == tenant_id,
                    LiveChatConversation.customer_identifier == customer_identifier,
                    LiveChatConversation.assigned_agent_id.isnot(None)
                )
            ).group_by(LiveChatConversation.assigned_agent_id).order_by(desc('count')).limit(3).all()
            
            preferred_agents = []
            for agent_id, count in agent_frequency:
                from app.live_chat.models import Agent
                agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
                if agent:
                    preferred_agents.append({
                        "agent_id": agent_id,
                        "agent_name": agent.display_name,
                        "conversation_count": count
                    })
            
            history["preferred_agents"] = preferred_agents
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting visitor history: {str(e)}")
            return {"is_returning": False, "error": str(e)}
    
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
            
            # Language routing
            if geolocation.get("country_code"):
                language_mapping = {
                    "ES": "Spanish", "FR": "French", "DE": "German",
                    "IT": "Italian", "PT": "Portuguese", "JP": "Japanese",
                    "CN": "Chinese", "KR": "Korean", "RU": "Russian"
                }
                suggested_language = language_mapping.get(geolocation["country_code"], "English")
                suggestions["routing_criteria"].append(f"Language: {suggested_language}")
            
            # Device-specific routing
            if device_info.get("device_type") == "mobile":
                suggestions["special_considerations"].append("Mobile user - prefer agents with mobile support expertise")
            
            # Returning visitor routing
            if visitor_history.get("is_returning") and visitor_history.get("preferred_agents"):
                preferred_agent = visitor_history["preferred_agents"][0]
                suggestions["recommended_agents"].append({
                    "agent_id": preferred_agent["agent_id"],
                    "agent_name": preferred_agent["agent_name"],
                    "reason": "Previous successful interactions",
                    "priority": 0.9
                })
                suggestions["routing_criteria"].append("Returning visitor - preferred agent available")
            
            # Satisfaction-based routing
            if visitor_history.get("conversation_outcomes", {}).get("abandoned", 0) > 2:
                suggestions["priority_score"] = 1.5  # Higher priority for customers with abandonment history
                suggestions["special_considerations"].append("Customer has history of abandoned conversations - assign experienced agent")
            
            # Get available agents for this tenant
            try:
                from app.live_chat.models import Agent, AgentSession
                available_agents = self.db.query(Agent).join(
                    AgentSession, Agent.id == AgentSession.agent_id
                ).filter(
                    and_(
                        Agent.tenant_id == tenant_id,
                        Agent.is_online == True,
                        Agent.status == "active",
                        AgentSession.logout_at.is_(None),
                        AgentSession.active_conversations < AgentSession.max_concurrent_chats
                    )
                ).all()
                
                # Add available agents to recommendations
                for agent in available_agents[:3]:  # Top 3 available agents
                    session = agent.sessions[0] if agent.sessions else None
                    suggestions["recommended_agents"].append({
                        "agent_id": agent.id,
                        "agent_name": agent.display_name,
                        "reason": "Available agent with capacity",
                        "priority": 0.7,
                        "current_load": session.active_conversations if session else 0,
                        "max_capacity": session.max_concurrent_chats if session else 3
                    })
                
            except Exception as e:
                logger.error(f"Error getting available agents: {str(e)}")
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
                data_collection_consent=True,  # Default consent for testing
                marketing_consent=False
            )
            
            self.db.add(customer_profile)
            self.db.commit()
            self.db.refresh(customer_profile)
            
            logger.info(f"Created new customer profile for {customer_identifier}")
            return customer_profile
            
        except Exception as e:
            logger.error(f"Error creating customer profile: {str(e)}")
            # Return a minimal profile object for fallback
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