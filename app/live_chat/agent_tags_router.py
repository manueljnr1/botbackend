# app/live_chat/agent_tags_router.py

import logging
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, desc, func
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from datetime import datetime, timedelta

from app.database import get_db
from app.live_chat.models import Agent, AgentStatus
from app.live_chat.models import (
    AgentTag, ConversationTagging, AgentTagPerformance, 
    SmartRoutingLog, agent_tags_association
)
from app.live_chat.smart_routing_service import SmartRoutingService, MessageAnalyzer
from app.live_chat.auth_router import get_current_agent
from app.tenants.router import get_tenant_from_api_key

logger = logging.getLogger(__name__)
router = APIRouter()

# Pydantic Models
class CreateTagRequest(BaseModel):
    name: str
    display_name: str
    category: str
    description: Optional[str] = None
    color: str = "#6366f1"
    icon: Optional[str] = None
    priority_weight: float = 1.0
    keywords: Optional[List[str]] = None
    routing_rules: Optional[Dict[str, Any]] = None

class UpdateTagRequest(BaseModel):
    display_name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    priority_weight: Optional[float] = None
    keywords: Optional[List[str]] = None
    routing_rules: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class AssignTagToAgentRequest(BaseModel):
    agent_id: int
    tag_id: int
    proficiency_level: int = 3  # 1-5 scale
    max_concurrent_for_tag: int = 2

class BulkTagAssignmentRequest(BaseModel):
    agent_id: int
    tag_assignments: List[Dict[str, Any]]  # [{"tag_id": 1, "proficiency_level": 4}, ...]

class TestRoutingRequest(BaseModel):
    message_content: str
    customer_identifier: Optional[str] = None
    handoff_context: Optional[Dict[str, Any]] = None

class TagResponse(BaseModel):
    id: int
    name: str
    display_name: str
    category: str
    description: Optional[str]
    color: str
    icon: Optional[str]
    priority_weight: float
    is_active: bool
    total_conversations: int
    success_rate: float
    average_satisfaction: float
    created_at: str

class AgentTagResponse(BaseModel):
    agent_id: int
    agent_name: str
    tags: List[Dict[str, Any]]
    total_conversations: int
    avg_satisfaction: float
    specializations: List[str]

# =============================================================================
# ADMIN ENDPOINTS (API KEY AUTHENTICATION)
# =============================================================================

@router.post("/admin/tags")
async def create_agent_tag(
    request: CreateTagRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Create a new agent tag for categorizing skills"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Check if tag name already exists for tenant
        existing_tag = db.query(AgentTag).filter(
            and_(
                AgentTag.tenant_id == tenant.id,
                AgentTag.name == request.name.lower()
            )
        ).first()
        
        if existing_tag:
            raise HTTPException(
                status_code=400, 
                detail=f"Tag '{request.name}' already exists"
            )
        
        # Create new tag
        new_tag = AgentTag(
            tenant_id=tenant.id,
            name=request.name.lower(),
            display_name=request.display_name,
            category=request.category.lower(),
            description=request.description,
            color=request.color,
            icon=request.icon,
            priority_weight=request.priority_weight,
            keywords=request.keywords,
            routing_rules=request.routing_rules
        )
        
        db.add(new_tag)
        db.commit()
        db.refresh(new_tag)
        
        logger.info(f"Created agent tag '{request.name}' for tenant {tenant.id}")
        
        return {
            "success": True,
            "message": f"Tag '{request.display_name}' created successfully",
            "tag_id": new_tag.id,
            "tag": {
                "id": new_tag.id,
                "name": new_tag.name,
                "display_name": new_tag.display_name,
                "category": new_tag.category,
                "color": new_tag.color,
                "priority_weight": new_tag.priority_weight
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning tag to agent: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to assign tag")

@router.delete("/admin/agents/{agent_id}/tags/{tag_id}")
async def remove_tag_from_agent(
    agent_id: int,
    tag_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Remove a tag from an agent"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Verify agent and tag belong to tenant
        agent = db.query(Agent).filter(
            and_(Agent.id == agent_id, Agent.tenant_id == tenant.id)
        ).first()
        
        tag = db.query(AgentTag).filter(
            and_(AgentTag.id == tag_id, AgentTag.tenant_id == tenant.id)
        ).first()
        
        if not agent or not tag:
            raise HTTPException(status_code=404, detail="Agent or tag not found")
        
        # Remove assignment
        db.execute(
            agent_tags_association.delete().where(
                and_(
                    agent_tags_association.c.agent_id == agent_id,
                    agent_tags_association.c.tag_id == tag_id
                )
            )
        )
        
        # Mark performance record as inactive
        performance = db.query(AgentTagPerformance).filter(
            and_(
                AgentTagPerformance.agent_id == agent_id,
                AgentTagPerformance.tag_id == tag_id
            )
        ).first()
        
        if performance:
            performance.is_available_for_tag = False
            performance.last_updated = datetime.utcnow()
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Tag '{tag.display_name}' removed from {agent.display_name}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing tag from agent: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to remove tag")

@router.post("/admin/agents/{agent_id}/tags/bulk")
async def bulk_assign_tags_to_agent(
    agent_id: int,
    request: BulkTagAssignmentRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Bulk assign multiple tags to an agent"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        agent = db.query(Agent).filter(
            and_(Agent.id == agent_id, Agent.tenant_id == tenant.id)
        ).first()
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        successful_assignments = []
        failed_assignments = []
        
        for assignment in request.tag_assignments:
            try:
                tag_id = assignment["tag_id"]
                proficiency_level = assignment.get("proficiency_level", 3)
                max_concurrent = assignment.get("max_concurrent_for_tag", 2)
                
                # Verify tag exists
                tag = db.query(AgentTag).filter(
                    and_(
                        AgentTag.id == tag_id,
                        AgentTag.tenant_id == tenant.id,
                        AgentTag.is_active == True
                    )
                ).first()
                
                if not tag:
                    failed_assignments.append({
                        "tag_id": tag_id,
                        "error": "Tag not found or inactive"
                    })
                    continue
                
                # Create or update assignment
                existing = db.query(agent_tags_association).filter(
                    and_(
                        agent_tags_association.c.agent_id == agent_id,
                        agent_tags_association.c.tag_id == tag_id
                    )
                ).first()
                
                if existing:
                    db.execute(
                        agent_tags_association.update().where(
                            and_(
                                agent_tags_association.c.agent_id == agent_id,
                                agent_tags_association.c.tag_id == tag_id
                            )
                        ).values(proficiency_level=proficiency_level)
                    )
                else:
                    db.execute(
                        agent_tags_association.insert().values(
                            agent_id=agent_id,
                            tag_id=tag_id,
                            proficiency_level=proficiency_level,
                            assigned_at=datetime.utcnow()
                        )
                    )
                
                # Create or update performance record
                performance = db.query(AgentTagPerformance).filter(
                    and_(
                        AgentTagPerformance.agent_id == agent_id,
                        AgentTagPerformance.tag_id == tag_id
                    )
                ).first()
                
                if not performance:
                    performance = AgentTagPerformance(
                        agent_id=agent_id,
                        tag_id=tag_id,
                        proficiency_level=proficiency_level,
                        max_concurrent_for_tag=max_concurrent
                    )
                    db.add(performance)
                else:
                    performance.proficiency_level = proficiency_level
                    performance.max_concurrent_for_tag = max_concurrent
                    performance.is_available_for_tag = True
                    performance.last_updated = datetime.utcnow()
                
                successful_assignments.append({
                    "tag_id": tag_id,
                    "tag_name": tag.display_name,
                    "proficiency_level": proficiency_level
                })
                
            except Exception as e:
                failed_assignments.append({
                    "tag_id": assignment.get("tag_id", "unknown"),
                    "error": str(e)
                })
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Bulk assignment completed for {agent.display_name}",
            "successful_assignments": successful_assignments,
            "failed_assignments": failed_assignments,
            "total_assigned": len(successful_assignments),
            "total_failed": len(failed_assignments)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk tag assignment: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to perform bulk assignment")

@router.get("/admin/agents-with-tags")
async def get_agents_with_tags(
    api_key: str = Header(..., alias="X-API-Key"),
    tag_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get all agents with their tag assignments"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Get agents with their tags
        agents = db.query(Agent).filter(
            and_(
                Agent.tenant_id == tenant.id,
                Agent.is_active == True
            )
        ).options(joinedload(Agent.tags)).all()
        
        agent_list = []
        for agent in agents:
            # Get tag performance data
            tag_performances = db.query(AgentTagPerformance).filter(
                AgentTagPerformance.agent_id == agent.id
            ).all()
            
            performance_by_tag = {perf.tag_id: perf for perf in tag_performances}
            
            agent_tags = []
            specializations = []
            
            for tag in agent.tags:
                # Filter by category if specified
                if category and tag.category != category.lower():
                    continue
                
                # Filter by specific tag if specified
                if tag_id and tag.id != tag_id:
                    continue
                
                performance = performance_by_tag.get(tag.id)
                
                tag_info = {
                    "tag_id": tag.id,
                    "name": tag.name,
                    "display_name": tag.display_name,
                    "category": tag.category,
                    "color": tag.color,
                    "proficiency_level": 3,  # Default
                    "total_conversations": 0,
                    "success_rate": 0.0,
                    "avg_satisfaction": 0.0,
                    "is_available": True
                }
                
                if performance:
                    tag_info.update({
                        "proficiency_level": performance.proficiency_level,
                        "total_conversations": performance.total_conversations,
                        "success_rate": (performance.successful_resolutions / 
                                       performance.total_conversations if performance.total_conversations > 0 else 0),
                        "avg_satisfaction": performance.customer_satisfaction_avg or 0.0,
                        "avg_resolution_time": performance.average_resolution_time or 0.0,
                        "is_available": performance.is_available_for_tag,
                        "max_concurrent": performance.max_concurrent_for_tag
                    })
                
                agent_tags.append(tag_info)
                
                # Add to specializations if high proficiency
                if tag_info["proficiency_level"] >= 4:
                    specializations.append(tag.display_name)
            
            # Skip agents with no matching tags if filtering
            if (tag_id or category) and not agent_tags:
                continue
            
            agent_data = {
                "agent_id": agent.id,
                "agent_name": agent.display_name,
                "email": agent.email,
                "is_online": agent.is_online,
                "total_conversations": agent.total_conversations,
                "avg_satisfaction": agent.customer_satisfaction_avg or 0.0,
                "tags": agent_tags,
                "specializations": specializations,
                "tag_count": len(agent_tags)
            }
            
            agent_list.append(agent_data)
        
        # Sort by tag count descending
        agent_list.sort(key=lambda x: x["tag_count"], reverse=True)
        
        return {
            "success": True,
            "total_agents": len(agent_list),
            "agents": agent_list
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agents with tags: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get agents with tags")

# =============================================================================
# SMART ROUTING ENDPOINTS
# =============================================================================

@router.post("/test-routing")
async def test_smart_routing(
    request: TestRoutingRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Test smart routing algorithm with sample message"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Analyze message content
        analyzer = MessageAnalyzer()
        detected_tags = analyzer.analyze_message(request.message_content)
        
        # Get matching tags from database
        db_tags = []
        for tag_data in detected_tags:
            tag = db.query(AgentTag).filter(
                and_(
                    AgentTag.tenant_id == tenant.id,
                    AgentTag.name == tag_data["tag_name"],
                    AgentTag.is_active == True
                )
            ).first()
            
            if tag:
                db_tags.append({
                    "tag_id": tag.id,
                    "tag_name": tag.name,
                    "display_name": tag.display_name,
                    "category": tag.category,
                    "confidence": tag_data["confidence"],
                    "keywords": tag_data["detected_keywords"],
                    "priority_weight": tag.priority_weight
                })
        
        # Get available agents
        routing_service = SmartRoutingService(db)
        available_agents = await routing_service._get_available_agents(tenant.id)
        
        # Score agents
        if available_agents and db_tags:
            # Create mock conversation context
            mock_context = {
                "customer_history": {"is_new": True},
                "urgency_indicators": {"is_urgent": False, "urgency_score": 0},
                "complexity_score": 2,
                "customer_sentiment": "neutral"
            }
            
            scored_agents = await routing_service._score_agents(
                available_agents, db_tags, mock_context, None
            )
        else:
            scored_agents = []
        
        return {
            "success": True,
            "message_content": request.message_content,
            "detected_tags": db_tags,
            "available_agents_count": len(available_agents),
            "routing_results": {
                "recommended_agent": scored_agents[0] if scored_agents else None,
                "alternative_agents": scored_agents[1:3] if len(scored_agents) > 1 else [],
                "total_scored_agents": len(scored_agents)
            },
            "analysis": {
                "confidence_level": "high" if db_tags and scored_agents else "low",
                "routing_method": "smart_tags" if db_tags and scored_agents else "fallback",
                "tag_matches": len(db_tags)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing smart routing: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to test routing")

@router.get("/routing-analytics")
async def get_routing_analytics(
    api_key: str = Header(..., alias="X-API-Key"),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Get routing analytics and performance insights"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        routing_service = SmartRoutingService(db)
        analytics = routing_service.get_routing_analytics(tenant.id, days)
        
        return {
            "success": True,
            **analytics
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting routing analytics: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get analytics")

# =============================================================================
# AGENT ENDPOINTS (Bearer Token Authentication)
# =============================================================================

@router.get("/agent/my-tags")
async def get_my_tags(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Get current agent's tags and performance"""
    try:
        # Get agent's tags with performance data
        agent_tags = db.query(AgentTag).join(agent_tags_association).filter(
            agent_tags_association.c.agent_id == current_agent.id
        ).all()
        
        tag_performances = db.query(AgentTagPerformance).filter(
            AgentTagPerformance.agent_id == current_agent.id
        ).all()
        
        performance_by_tag = {perf.tag_id: perf for perf in tag_performances}
        
        my_tags = []
        for tag in agent_tags:
            performance = performance_by_tag.get(tag.id)
            
            tag_info = {
                "tag_id": tag.id,
                "name": tag.name,
                "display_name": tag.display_name,
                "category": tag.category,
                "description": tag.description,
                "color": tag.color,
                "proficiency_level": 3,
                "total_conversations": 0,
                "success_rate": 0.0,
                "avg_satisfaction": 0.0,
                "avg_resolution_time": 0.0,
                "recent_performance": {}
            }
            
            if performance:
                tag_info.update({
                    "proficiency_level": performance.proficiency_level,
                    "total_conversations": performance.total_conversations,
                    "success_rate": (performance.successful_resolutions / 
                                   performance.total_conversations if performance.total_conversations > 0 else 0),
                    "avg_satisfaction": performance.customer_satisfaction_avg or 0.0,
                    "avg_resolution_time": performance.average_resolution_time or 0.0,
                    "conversations_last_30_days": performance.conversations_last_30_days,
                    "satisfaction_last_30_days": performance.satisfaction_last_30_days or 0.0,
                    "is_certified": performance.certified,
                    "last_training_date": performance.last_training_date.isoformat() if performance.last_training_date else None
                })
            
            my_tags.append(tag_info)
        
        # Group by category
        categories = {}
        for tag in my_tags:
            category = tag["category"]
            if category not in categories:
                categories[category] = []
            categories[category].append(tag)
        
        return {
            "success": True,
            "agent_id": current_agent.id,
            "agent_name": current_agent.display_name,
            "total_tags": len(my_tags),
            "categories": categories,
            "tags": my_tags,
            "specializations": [tag["display_name"] for tag in my_tags if tag["proficiency_level"] >= 4]
        }
        
    except Exception as e:
        logger.error(f"Error getting agent tags: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get tags")

@router.get("/agent/available-tags")
async def get_available_tags_for_agent(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """Get all available tags that can be assigned to the agent"""
    try:
        # Get all active tags for tenant
        all_tags = db.query(AgentTag).filter(
            and_(
                AgentTag.tenant_id == current_agent.tenant_id,
                AgentTag.is_active == True
            )
        ).order_by(AgentTag.category, AgentTag.name).all()
        
        # Get agent's current tags
        current_tag_ids = {
            tag_id for tag_id, in db.query(agent_tags_association.c.tag_id).filter(
                agent_tags_association.c.agent_id == current_agent.id
            ).all()
        }
        
        available_tags = []
        for tag in all_tags:
            tag_info = {
                "tag_id": tag.id,
                "name": tag.name,
                "display_name": tag.display_name,
                "category": tag.category,
                "description": tag.description,
                "color": tag.color,
                "icon": tag.icon,
                "priority_weight": tag.priority_weight,
                "keywords": tag.keywords or [],
                "is_assigned": tag.id in current_tag_ids
            }
            
            # Add usage statistics
            agent_count = db.query(func.count(agent_tags_association.c.agent_id)).filter(
                agent_tags_association.c.tag_id == tag.id
            ).scalar() or 0
            
            tag_info["agents_with_tag"] = agent_count
            
            available_tags.append(tag_info)
        
        # Group by category
        categories = {}
        for tag in available_tags:
            category = tag["category"]
            if category not in categories:
                categories[category] = {
                    "tags": [],
                    "assigned_count": 0,
                    "available_count": 0
                }
            categories[category]["tags"].append(tag)
            if tag["is_assigned"]:
                categories[category]["assigned_count"] += 1
            else:
                categories[category]["available_count"] += 1
        
        return {
            "success": True,
            "total_tags": len(available_tags),
            "assigned_tags": len(current_tag_ids),
            "available_for_assignment": len(available_tags) - len(current_tag_ids),
            "categories": categories,
            "tags": available_tags
        }
        
    except Exception as e:
        logger.error(f"Error getting available tags: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get available tags")

# =============================================================================
# UTILITY ENDPOINTS
# =============================================================================

@router.get("/categories")
async def get_tag_categories(
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Get all tag categories with statistics"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        categories = db.query(
            AgentTag.category,
            func.count(AgentTag.id).label('tag_count'),
            func.avg(AgentTag.priority_weight).label('avg_priority')
        ).filter(
            and_(
                AgentTag.tenant_id == tenant.id,
                AgentTag.is_active == True
            )
        ).group_by(AgentTag.category).all()
        
        category_list = []
        for category, tag_count, avg_priority in categories:
            # Get agent count for this category
            agent_count = db.query(func.count(func.distinct(agent_tags_association.c.agent_id))).join(
                AgentTag
            ).filter(
                and_(
                    AgentTag.category == category,
                    AgentTag.tenant_id == tenant.id
                )
            ).scalar() or 0
            
            category_list.append({
                "category": category,
                "tag_count": tag_count,
                "agent_count": agent_count,
                "avg_priority": round(avg_priority or 1.0, 2)
            })
        
        return {
            "success": True,
            "categories": category_list
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tag categories: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get categories")(f"Error creating agent tag: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create tag")

@router.get("/admin/tags")
async def get_agent_tags(
    api_key: str = Header(..., alias="X-API-Key"),
    category: Optional[str] = Query(None),
    include_stats: bool = Query(True),
    db: Session = Depends(get_db)
):
    """Get all agent tags for the tenant"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Build query
        query = db.query(AgentTag).filter(AgentTag.tenant_id == tenant.id)
        
        if category:
            query = query.filter(AgentTag.category == category.lower())
        
        tags = query.order_by(AgentTag.category, AgentTag.name).all()
        
        tag_list = []
        for tag in tags:
            tag_data = {
                "id": tag.id,
                "name": tag.name,
                "display_name": tag.display_name,
                "category": tag.category,
                "description": tag.description,
                "color": tag.color,
                "icon": tag.icon,
                "priority_weight": tag.priority_weight,
                "is_active": tag.is_active,
                "keywords": tag.keywords or [],
                "created_at": tag.created_at.isoformat()
            }
            
            if include_stats:
                # Get agent count with this tag
                agent_count = db.query(func.count(agent_tags_association.c.agent_id)).filter(
                    agent_tags_association.c.tag_id == tag.id
                ).scalar() or 0
                
                # Get performance stats
                avg_satisfaction = db.query(func.avg(AgentTagPerformance.customer_satisfaction_avg)).filter(
                    AgentTagPerformance.tag_id == tag.id
                ).scalar() or 0.0
                
                total_conversations = db.query(func.sum(AgentTagPerformance.total_conversations)).filter(
                    AgentTagPerformance.tag_id == tag.id
                ).scalar() or 0
                
                tag_data.update({
                    "agent_count": agent_count,
                    "total_conversations": total_conversations,
                    "average_satisfaction": round(avg_satisfaction, 2)
                })
            
            tag_list.append(tag_data)
        
        # Group by category
        categories = {}
        for tag in tag_list:
            category = tag["category"]
            if category not in categories:
                categories[category] = []
            categories[category].append(tag)
        
        return {
            "success": True,
            "total_tags": len(tag_list),
            "categories": categories,
            "tags": tag_list
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent tags: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get tags")

@router.put("/admin/tags/{tag_id}")
async def update_agent_tag(
    tag_id: int,
    request: UpdateTagRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Update an agent tag"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        tag = db.query(AgentTag).filter(
            and_(
                AgentTag.id == tag_id,
                AgentTag.tenant_id == tenant.id
            )
        ).first()
        
        if not tag:
            raise HTTPException(status_code=404, detail="Tag not found")
        
        # Update fields
        update_data = request.dict(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(tag, field):
                setattr(tag, field, value)
        
        tag.updated_at = datetime.utcnow()
        db.commit()
        
        return {
            "success": True,
            "message": f"Tag '{tag.display_name}' updated successfully",
            "tag_id": tag.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent tag: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update tag")

@router.delete("/admin/tags/{tag_id}")
async def delete_agent_tag(
    tag_id: int,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Delete an agent tag (soft delete)"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        tag = db.query(AgentTag).filter(
            and_(
                AgentTag.id == tag_id,
                AgentTag.tenant_id == tenant.id
            )
        ).first()
        
        if not tag:
            raise HTTPException(status_code=404, detail="Tag not found")
        
        # Check if tag is in use
        agents_with_tag = db.query(func.count(agent_tags_association.c.agent_id)).filter(
            agent_tags_association.c.tag_id == tag_id
        ).scalar()
        
        if agents_with_tag > 0:
            # Soft delete - deactivate instead of removing
            tag.is_active = False
            tag.updated_at = datetime.utcnow()
            db.commit()
            
            return {
                "success": True,
                "message": f"Tag '{tag.display_name}' deactivated (was assigned to {agents_with_tag} agents)",
                "action": "deactivated"
            }
        else:
            # Hard delete if not in use
            db.delete(tag)
            db.commit()
            
            return {
                "success": True,
                "message": f"Tag '{tag.display_name}' deleted successfully",
                "action": "deleted"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting agent tag: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete tag")

@router.post("/admin/agents/{agent_id}/tags")
async def assign_tag_to_agent(
    agent_id: int,
    request: AssignTagToAgentRequest,
    api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """Assign a tag to an agent with proficiency level"""
    try:
        tenant = get_tenant_from_api_key(api_key, db)
        
        # Verify agent exists and belongs to tenant
        agent = db.query(Agent).filter(
            and_(
                Agent.id == agent_id,
                Agent.tenant_id == tenant.id
            )
        ).first()
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Verify tag exists and belongs to tenant
        tag = db.query(AgentTag).filter(
            and_(
                AgentTag.id == request.tag_id,
                AgentTag.tenant_id == tenant.id,
                AgentTag.is_active == True
            )
        ).first()
        
        if not tag:
            raise HTTPException(status_code=404, detail="Tag not found or inactive")
        
        # Check if assignment already exists
        existing_assignment = db.query(agent_tags_association).filter(
            and_(
                agent_tags_association.c.agent_id == agent_id,
                agent_tags_association.c.tag_id == request.tag_id
            )
        ).first()
        
        if existing_assignment:
            # Update proficiency level
            db.execute(
                agent_tags_association.update().where(
                    and_(
                        agent_tags_association.c.agent_id == agent_id,
                        agent_tags_association.c.tag_id == request.tag_id
                    )
                ).values(proficiency_level=request.proficiency_level)
            )
        else:
            # Create new assignment
            db.execute(
                agent_tags_association.insert().values(
                    agent_id=agent_id,
                    tag_id=request.tag_id,
                    proficiency_level=request.proficiency_level,
                    assigned_at=datetime.utcnow()
                )
            )
        
        # Create or update performance record
        performance = db.query(AgentTagPerformance).filter(
            and_(
                AgentTagPerformance.agent_id == agent_id,
                AgentTagPerformance.tag_id == request.tag_id
            )
        ).first()
        
        if not performance:
            performance = AgentTagPerformance(
                agent_id=agent_id,
                tag_id=request.tag_id,
                proficiency_level=request.proficiency_level,
                max_concurrent_for_tag=request.max_concurrent_for_tag
            )
            db.add(performance)
        else:
            performance.proficiency_level = request.proficiency_level
            performance.max_concurrent_for_tag = request.max_concurrent_for_tag
            performance.last_updated = datetime.utcnow()
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Tag '{tag.display_name}' assigned to {agent.display_name} with proficiency level {request.proficiency_level}",
            "assignment": {
                "agent_id": agent_id,
                "agent_name": agent.display_name,
                "tag_id": request.tag_id,
                "tag_name": tag.display_name,
                "proficiency_level": request.proficiency_level
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error