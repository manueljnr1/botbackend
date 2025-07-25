from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

class ConversationFilterRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    session_id: Optional[str] = None
    category: Optional[str] = None
    sentiment: Optional[str] = None

class LocationAnalytics(BaseModel):
    country: str
    city: str
    region: str
    count: int
    percentage: float

class TopicAnalytics(BaseModel):
    topic: str
    count: int
    sentiment_distribution: Dict[str, int]

class CategoryAnalytics(BaseModel):
    category: str
    count: int
    avg_sentiment: float
    avg_rating: Optional[float]

class RatingResponse(BaseModel):
    rating: int
    feedback: Optional[str] = None
    success: bool

class JourneyStage(BaseModel):
    stage: str
    timestamp: datetime
    action: str

class CustomerJourney(BaseModel):
    session_id: str
    user_identifier: str
    journey_stages: List[JourneyStage]
    total_duration: int  # seconds
    conversion_stage: Optional[str]

class SentimentAnalysis(BaseModel):
    session_id: str
    overall_sentiment: str
    sentiment_score: float
    mood_changes: List[Dict[str, Any]]