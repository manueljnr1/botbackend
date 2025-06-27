# app/live_chat/free_geolocation_service.py

import logging
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import httpx
from functools import lru_cache

logger = logging.getLogger(__name__)

class FreeGeolocationService:
    """
    Free geolocation service using multiple API providers
    No database downloads required - works out of the box!
    """
    
    def __init__(self):
        self.cache = {}  # Simple in-memory cache
        self.cache_ttl = timedelta(hours=24)  # Cache for 24 hours
        
        # Free API providers (in order of preference)
        self.providers = [
            {
                "name": "ip-api",
                "url": "http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,region,regionName,city,lat,lon,timezone,isp",
                "rate_limit": 45,  # 45 requests per minute
                "monthly_limit": 1000
            },
            {
                "name": "ipinfo",
                "url": "https://ipinfo.io/{ip}/json",
                "rate_limit": 50,  # 50 requests per minute
                "monthly_limit": 50000
            },
            {
                "name": "freeipapi",
                "url": "https://freeipapi.com/api/json/{ip}",
                "rate_limit": 60,  # 60 requests per minute
                "monthly_limit": 1000
            }
        ]
    
    async def get_location(self, ip_address: str) -> Dict[str, any]:
        """Get geolocation using free APIs with caching and fallbacks"""
        try:
            # Skip private/local IPs
            if not self._is_public_ip(ip_address):
                return self._get_fallback_location("private_ip")
            
            # Check cache first
            cached_result = self._get_from_cache(ip_address)
            if cached_result:
                logger.debug(f"Using cached location for {ip_address}")
                return cached_result
            
            # Try each provider until one succeeds
            for provider in self.providers:
                try:
                    location_data = await self._query_provider(provider, ip_address)
                    if location_data and location_data.get("country"):
                        # Cache the successful result
                        self._cache_result(ip_address, location_data)
                        return location_data
                except Exception as e:
                    logger.warning(f"Provider {provider['name']} failed: {str(e)}")
                    continue
            
            # All providers failed - return fallback
            logger.warning(f"All geolocation providers failed for {ip_address}")
            return self._get_fallback_location("api_failure")
            
        except Exception as e:
            logger.error(f"Geolocation service error: {str(e)}")
            return self._get_fallback_location("service_error")
    
    async def _query_provider(self, provider: Dict, ip_address: str) -> Optional[Dict]:
        """Query a specific geolocation provider"""
        url = provider["url"].format(ip=ip_address)
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            return self._normalize_response(provider["name"], data)
    
    def _normalize_response(self, provider: str, data: Dict) -> Dict:
        """Normalize different API responses to common format"""
        normalized = {
            "ip_address": data.get("query") or data.get("ip", "unknown"),
            "country": None,
            "country_code": None,
            "region": None,
            "city": None,
            "latitude": None,
            "longitude": None,
            "timezone": None,
            "isp": None,
            "detection_method": f"api_{provider}",
            "accuracy": "medium"
        }
        
        if provider == "ip-api":
            if data.get("status") == "success":
                normalized.update({
                    "country": data.get("country"),
                    "country_code": data.get("countryCode"),
                    "region": data.get("regionName"),
                    "city": data.get("city"),
                    "latitude": data.get("lat"),
                    "longitude": data.get("lon"),
                    "timezone": data.get("timezone"),
                    "isp": data.get("isp")
                })
        
        elif provider == "ipinfo":
            # IPInfo format: {"ip": "8.8.8.8", "city": "Mountain View", "region": "California", "country": "US", "loc": "37.4056,-122.0775", "timezone": "America/Los_Angeles"}
            if "country" in data:
                loc = data.get("loc", "").split(",")
                normalized.update({
                    "country": self._get_country_name(data.get("country")),
                    "country_code": data.get("country"),
                    "region": data.get("region"),
                    "city": data.get("city"),
                    "latitude": float(loc[0]) if len(loc) > 0 and loc[0] else None,
                    "longitude": float(loc[1]) if len(loc) > 1 and loc[1] else None,
                    "timezone": data.get("timezone"),
                    "isp": data.get("org")
                })
        
        elif provider == "freeipapi":
            normalized.update({
                "country": data.get("countryName"),
                "country_code": data.get("countryCode"),
                "region": data.get("regionName"),
                "city": data.get("cityName"),
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "timezone": data.get("timeZone"),
                "isp": data.get("ispName")
            })
        
        return normalized
    
    def _is_public_ip(self, ip: str) -> bool:
        """Check if IP is public (not private/local)"""
        try:
            import ipaddress
            ip_obj = ipaddress.ip_address(ip)
            return not (ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local)
        except ValueError:
            return False
    
    def _get_from_cache(self, ip: str) -> Optional[Dict]:
        """Get cached result if not expired"""
        cache_key = hashlib.md5(ip.encode()).hexdigest()
        
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if datetime.utcnow() - timestamp < self.cache_ttl:
                cached_data["detection_method"] += "_cached"
                return cached_data
            else:
                # Remove expired cache
                del self.cache[cache_key]
        
        return None
    
    def _cache_result(self, ip: str, data: Dict):
        """Cache successful result"""
        cache_key = hashlib.md5(ip.encode()).hexdigest()
        self.cache[cache_key] = (data.copy(), datetime.utcnow())
        
        # Simple cache cleanup - remove old entries
        if len(self.cache) > 1000:  # Keep cache size reasonable
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]
    
    def _get_fallback_location(self, reason: str) -> Dict:
        """Return fallback location data when geolocation fails"""
        return {
            "ip_address": "unknown",
            "country": None,
            "country_code": None,
            "region": None,
            "city": None,
            "latitude": None,
            "longitude": None,
            "timezone": None,
            "isp": None,
            "detection_method": f"fallback_{reason}",
            "accuracy": "none"
        }
    
    def _get_country_name(self, country_code: str) -> str:
        """Convert country code to country name"""
        country_mapping = {
            "US": "United States", "GB": "United Kingdom", "CA": "Canada",
            "AU": "Australia", "DE": "Germany", "FR": "France", "ES": "Spain",
            "IT": "Italy", "NL": "Netherlands", "BE": "Belgium", "CH": "Switzerland",
            "AT": "Austria", "SE": "Sweden", "NO": "Norway", "DK": "Denmark",
            "FI": "Finland", "PL": "Poland", "CZ": "Czech Republic", "HU": "Hungary",
            "RO": "Romania", "BG": "Bulgaria", "HR": "Croatia", "SI": "Slovenia",
            "SK": "Slovakia", "LT": "Lithuania", "LV": "Latvia", "EE": "Estonia",
            "IE": "Ireland", "PT": "Portugal", "GR": "Greece", "CY": "Cyprus",
            "MT": "Malta", "LU": "Luxembourg", "JP": "Japan", "KR": "South Korea",
            "CN": "China", "IN": "India", "BR": "Brazil", "MX": "Mexico",
            "AR": "Argentina", "CL": "Chile", "CO": "Colombia", "PE": "Peru",
            "VE": "Venezuela", "RU": "Russia", "UA": "Ukraine", "TR": "Turkey",
            "SA": "Saudi Arabia", "AE": "United Arab Emirates", "IL": "Israel",
            "EG": "Egypt", "ZA": "South Africa", "NG": "Nigeria", "KE": "Kenya",
            "GH": "Ghana", "TZ": "Tanzania", "UG": "Uganda", "ZW": "Zimbabwe",
            "BW": "Botswana", "ZM": "Zambia", "MW": "Malawi", "MZ": "Mozambique",
            "MG": "Madagascar", "MU": "Mauritius", "SC": "Seychelles"
        }
        return country_mapping.get(country_code, country_code)
    
    def get_usage_stats(self) -> Dict:
        """Get usage statistics"""
        return {
            "cache_size": len(self.cache),
            "providers_available": len(self.providers),
            "cache_hit_ratio": "N/A",  # Would need request tracking
            "total_requests": "N/A"   # Would need request tracking
        }


# Updated CustomerDetectionService that uses free APIs instead of GeoIP database
class FreeCustomerDetectionService:
    """Updated customer detection service using free geolocation APIs"""
    
    def __init__(self, db):
        self.db = db
        self.geolocation_service = FreeGeolocationService()
    
    async def detect_geolocation(self, ip_address: str) -> Dict:
        """Detect geolocation using free APIs instead of local database"""
        return await self.geolocation_service.get_location(ip_address)
    
    # ... rest of the methods remain the same as CustomerDetectionService


# Quick test function
async def test_free_geolocation():
    """Test the free geolocation service"""
    service = FreeGeolocationService()
    
    test_ips = [
        "8.8.8.8",        # Google DNS
        "1.1.1.1",        # Cloudflare DNS  
        "208.67.222.222", # OpenDNS
        "your.real.ip"    # Replace with actual IP
    ]
    
    for ip in test_ips:
        print(f"\n🔍 Testing IP: {ip}")
        result = await service.get_location(ip)
        print(f"Country: {result.get('country', 'Unknown')}")
        print(f"City: {result.get('city', 'Unknown')}")
        print(f"Method: {result.get('detection_method', 'Unknown')}")
        print(f"Accuracy: {result.get('accuracy', 'Unknown')}")

if __name__ == "__main__":
    asyncio.run(test_free_geolocation())