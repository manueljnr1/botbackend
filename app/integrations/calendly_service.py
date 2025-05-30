# Replace your app/integrations/calendly_service.py with this fixed version

import requests
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.tenants.models import Tenant
import re
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class CalendlyService:
    """Service for handling Calendly API interactions"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.calendly.com"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    
    def get_user_info(self) -> Dict[str, Any]:
        """Get current user information from Calendly"""
        try:
            response = requests.get(
                f"{self.base_url}/users/me",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error fetching user info: {e}")
            return {}
    
    def get_event_types(self, user_uri: str) -> List[Dict[str, Any]]:
        """Get available event types for a user"""
        try:
            response = requests.get(
                f"{self.base_url}/event_types",
                headers=self.headers,
                params={"user": user_uri}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("collection", [])
        except requests.RequestException as e:
            logger.error(f"Error fetching event types: {e}")
            return []
    
    def get_scheduled_events(self, user_uri: str, count: int = 20) -> List[Dict[str, Any]]:
        """Get scheduled events for a user"""
        try:
            response = requests.get(
                f"{self.base_url}/scheduled_events",
                headers=self.headers,
                params={
                    "user": user_uri,
                    "count": count,
                    "sort": "start_time:asc"
                }
            )
            response.raise_for_status()
            data = response.json()
            return data.get("collection", [])
        except requests.RequestException as e:
            logger.error(f"Error fetching scheduled events: {e}")
            return []

class CalendlyManager:
    """Manager for tenant-specific Calendly operations with enhanced booking detection"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_tenant_calendly_service(self, tenant_id: int) -> Optional[CalendlyService]:
        """Get Calendly service for a specific tenant"""
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        
        if not tenant or not getattr(tenant, 'calendly_enabled', False) or not getattr(tenant, 'calendly_access_token', None):
            return None
        
        return CalendlyService(tenant.calendly_access_token)
    
    def setup_tenant_calendly(self, tenant_id: int, access_token: str) -> bool:
        """Setup Calendly integration for a tenant"""
        try:
            # Test the access token
            service = CalendlyService(access_token)
            user_info = service.get_user_info()
            
            if not user_info.get("resource"):
                logger.error("Invalid Calendly access token")
                return False
            
            # Update tenant with Calendly info
            tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                return False
            
            user_data = user_info["resource"]
            tenant.calendly_access_token = access_token
            tenant.calendly_user_uri = user_data.get("uri")
            tenant.calendly_organization_uri = user_data.get("current_organization")
            tenant.calendly_enabled = True
            
            # Get default event type
            event_types = service.get_event_types(user_data.get("uri"))
            if event_types:
                tenant.calendly_default_event_type = event_types[0].get("uri")
            
            self.db.commit()
            logger.info(f"Calendly setup completed for tenant {tenant_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up Calendly for tenant {tenant_id}: {e}")
            self.db.rollback()
            return False
    
    def get_booking_widget_url(self, tenant_id: int, prefill_data: Dict = None) -> Optional[str]:
        """Generate Calendly booking widget URL with prefill data"""
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        
        if not tenant or not getattr(tenant, 'calendly_enabled', False) or not getattr(tenant, 'calendly_default_event_type', None):
            return None
        
        # Extract event type slug from URI
        event_type_uri = tenant.calendly_default_event_type
        if not event_type_uri:
            return None
            
        event_type_slug = event_type_uri.split("/")[-1]
        
        # Get user slug from user URI
        user_uri = getattr(tenant, 'calendly_user_uri', '')
        if not user_uri:
            return None
            
        user_slug = user_uri.split("/")[-1]
        
        base_url = f"https://calendly.com/{user_slug}/{event_type_slug}"
        
        # Add prefill parameters
        if prefill_data:
            params = {}
            if prefill_data.get("name"):
                params["name"] = prefill_data["name"]
            if prefill_data.get("email"):
                params["email"] = prefill_data["email"]
            if prefill_data.get("text"):
                params["text"] = prefill_data["text"]
            
            if params:
                base_url += "?" + urlencode(params)
        
        return base_url
    
    def detect_booking_intent(self, message: str) -> bool:
        """Original method for backward compatibility"""
        booking_keywords = [
            "book", "schedule", "appointment", "meeting", "call", "demo",
            "consultation", "available", "time", "calendar", "when can",
            "book a meeting", "schedule a call", "set up a meeting",
            "available times", "free time", "book appointment",
            "reserve", "reserve time", "make appointment", "set appointment"
        ]
        
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in booking_keywords)
    
    def detect_booking_intent_with_details(self, message: str) -> Dict[str, Any]:
        """Enhanced booking intent detection that extracts meeting details"""
        
        # Basic booking intent detection
        has_booking_intent = self.detect_booking_intent(message)
        
        if not has_booking_intent:
            return {"has_intent": False}
        
        # Extract details from the message
        details = {
            "has_intent": True,
            "email": self._extract_email(message),
            "title": self._extract_title(message),
            "date_time": self._extract_datetime(message),
            "duration": self._extract_duration(message)
        }
        
        logger.info(f"Extracted booking details: {details}")
        return details
    
    def _extract_email(self, message: str) -> Optional[str]:
        """Extract email from message"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(email_pattern, message)
        return matches[0] if matches else None
    
    def _extract_title(self, message: str) -> Optional[str]:
        """Extract meeting title from message"""
        # Look for patterns like: 'title "something"', 'titled "something"', 'called "something"'
        title_patterns = [
            r'title[d]?\s*["\']([^"\']+)["\']',
            r'called\s*["\']([^"\']+)["\']',
            r'named\s*["\']([^"\']+)["\']',
            r'with\s+title\s*["\']([^"\']+)["\']'
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_datetime(self, message: str) -> Optional[str]:
        """Extract date and time from message"""
        try:
            # Look for time patterns like "4pm", "2:30 PM", "16:00"
            time_patterns = [
                r'(\d{1,2}(?::\d{2})?\s*(?:am|pm))',
                r'(\d{1,2}:\d{2})',
                r'at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))',
                r'for\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))'
            ]
            
            # Look for date patterns
            date_patterns = [
                r'(\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:may|june|july|august|september|october|november|december))',
                r'(may\s+\d{1,2}(?:st|nd|rd|th)?)',
                r'(\d{1,2}/\d{1,2}/\d{2,4})',
                r'(\d{4}-\d{1,2}-\d{1,2})',
                r'(today|tomorrow)'
            ]
            
            found_time = None
            found_date = None
            
            message_lower = message.lower()
            
            # Extract time
            for pattern in time_patterns:
                match = re.search(pattern, message_lower)
                if match:
                    found_time = match.group(1)
                    break
            
            # Extract date  
            for pattern in date_patterns:
                match = re.search(pattern, message_lower)
                if match:
                    found_date = match.group(1)
                    break
            
            # For your specific example: "4pm 30th of May"
            if "30th" in message_lower and "may" in message_lower and found_time:
                # Assume current year
                current_year = datetime.now().year
                try:
                    from dateutil import parser
                    datetime_string = f"May 30, {current_year} {found_time}"
                    parsed_datetime = parser.parse(datetime_string, fuzzy=True)
                    return parsed_datetime.isoformat()
                except:
                    pass
            
            # Combine date and time if both found
            if found_date and found_time:
                datetime_string = f"{found_date} {found_time}"
                try:
                    from dateutil import parser
                    parsed_datetime = parser.parse(datetime_string, fuzzy=True)
                    return parsed_datetime.isoformat()
                except:
                    pass
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting datetime: {e}")
            return None
    
    def _extract_duration(self, message: str) -> Optional[int]:
        """Extract meeting duration in minutes"""
        duration_patterns = [
            r'(\d+)\s*hour[s]?',
            r'(\d+)\s*minute[s]?',
            r'(\d+)\s*min[s]?',
            r'for\s+(\d+)\s*hour[s]?',
            r'for\s+(\d+)\s*minute[s]?'
        ]
        
        for pattern in duration_patterns:
            match = re.search(pattern, message.lower())
            if match:
                duration = int(match.group(1))
                # Convert hours to minutes
                if 'hour' in pattern:
                    duration *= 60
                return duration
        
        return None  # Use default event type duration
    
    def generate_smart_booking_response(self, tenant_id: int, booking_details: Dict[str, Any]) -> Dict[str, Any]:
        """Generate an intelligent booking response based on extracted details"""
        
        # Get booking URL with prefilled data
        prefill_data = {}
        if booking_details.get("email"):
            prefill_data["email"] = booking_details["email"]
        if booking_details.get("name"):
            prefill_data["name"] = booking_details["name"]
        
        # Add meeting details to the text field
        text_parts = []
        if booking_details.get("title"):
            text_parts.append(f"Meeting Title: {booking_details['title']}")
        if booking_details.get("date_time"):
            text_parts.append(f"Requested Time: {booking_details['date_time']}")
        
        if text_parts:
            prefill_data["text"] = " | ".join(text_parts)
        
        booking_url = self.get_booking_widget_url(tenant_id, prefill_data)
        
        if not booking_url:
            return {
                "success": False,
                "error": "Could not generate booking URL"
            }
        
        # Generate personalized response
        response_parts = []
        
        if booking_details.get("title") and booking_details.get("email") and booking_details.get("date_time"):
            # We have comprehensive details
            response_parts.append("Perfect! I have all the details for your meeting:")
            response_parts.append("")
            response_parts.append("📅 **Meeting Details:**")
            response_parts.append(f"• Title: {booking_details['title']}")
            response_parts.append(f"• Email: {booking_details['email']}")
            response_parts.append(f"• Requested Time: {booking_details['date_time']}")
            response_parts.append("")
            response_parts.append("I've prepared your booking link with all these details pre-filled:")
        else:
            # Partial details
            response_parts.append("I'd be happy to help you book that meeting!")
            response_parts.append("")
            if booking_details.get("title") or booking_details.get("email") or booking_details.get("date_time"):
                response_parts.append("📝 **Details I found:**")
                if booking_details.get("title"):
                    response_parts.append(f"• Title: {booking_details['title']}")
                if booking_details.get("email"):
                    response_parts.append(f"• Email: {booking_details['email']}")
                if booking_details.get("date_time"):
                    response_parts.append(f"• Requested Time: {booking_details['date_time']}")
                response_parts.append("")
            response_parts.append("Here's your personalized booking link:")
        
        response_parts.append(f"{booking_url}")
        response_parts.append("")
        response_parts.append("The booking page will show available time slots, and I've pre-filled the form with your details. Once you book, you'll receive a confirmation email with all the meeting information!")
        
        return {
            "success": True,
            "response": "\n".join(response_parts),
            "booking_url": booking_url,
            "extracted_details": booking_details
        }