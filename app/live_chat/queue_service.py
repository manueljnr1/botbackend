# app/live_chat/enhanced_queue_service.py
# Enhanced version of queue_service.py with smart routing integration

import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import List, Dict, Optional, Any
import json
from collections import defaultdict

from app.live_chat.models import (
    LiveChatConversation, ChatQueue, Agent, AgentSession, 
    ConversationStatus, AgentStatus, LiveChatSettings
)
from app.live_chat.agent_tags_router import (
    AgentTag, ConversationTagging, AgentTagPerformance, SmartRoutingLog
)
from app.live_chat.smart_routing_service import SmartRoutingService


logger = logging.getLogger(__name__)


class LiveChatQueueService:
    """Enhanced queue service with intelligent routing using agent tags"""
    
    def __init__(self, db: Session):
        self.db = db
        self.smart_routing = SmartRoutingService(db)



    def get_queue_status(self, tenant_id: int) -> Dict:
        """
        Returns the live chat queue status for a specific tenant.
        """
        try:
            waiting_count = self.db.query(ChatQueue).filter(
                ChatQueue.status == "waiting",
                ChatQueue.tenant_id == tenant_id
            ).count()

            assigned_count = self.db.query(ChatQueue).filter(
                ChatQueue.status == "assigned",
                ChatQueue.tenant_id == tenant_id
            ).count()

            return {
                "success": True,
                "waiting": waiting_count,
                "assigned": assigned_count
            }
        except Exception as e:
            logger.error(f"Error in get_queue_status: {e}")
            return {"success": False, "error": str(e)}




    
    def add_to_queue(self, conversation_id: int, priority="normal", 
                    preferred_agent_id: int = None, assignment_criteria: Dict = None) -> Dict:
        """Add conversation to queue - basic method"""
        try:
            # Get conversation details
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")
            
            # Create queue entry
            queue_entry = ChatQueue(
                conversation_id=conversation_id,
                tenant_id=conversation.tenant_id,
                priority=priority,  # String value like "normal", "high", etc.
                status="waiting",
                preferred_agent_id=preferred_agent_id,
                assignment_criteria=json.dumps(assignment_criteria) if assignment_criteria else None,
                queued_at=datetime.utcnow(),
                position=self._get_next_position(conversation.tenant_id)
            )
            
            self.db.add(queue_entry)
            
            # Update conversation
            conversation.status = ConversationStatus.QUEUED
            conversation.queue_entry_time = datetime.utcnow()
            conversation.queue_position = queue_entry.position
            
            self.db.commit()
            self.db.refresh(queue_entry)
            
            return {
                "success": True,
                "queue_id": queue_entry.id,
                "position": queue_entry.position,
                "estimated_wait_time": self._calculate_wait_time(conversation.tenant_id, queue_entry.position)
            }
            
        except Exception as e:
            logger.error(f"Error adding to queue: {str(e)}")
            self.db.rollback()
            return {"success": False, "error": str(e)}

    # 🆕 ADD THESE HELPER METHODS TOO:
    def _get_next_position(self, tenant_id: int) -> int:
        """Get next position in queue for tenant"""
        try:
            max_position = self.db.query(func.max(ChatQueue.position)).filter(
                ChatQueue.tenant_id == tenant_id,
                ChatQueue.status == "waiting"
            ).scalar()
            
            return (max_position or 0) + 1
            
        except Exception as e:
            logger.error(f"Error getting next position: {str(e)}")
            return 1

    def _calculate_wait_time(self, tenant_id: int, position: int) -> int:
        """Calculate estimated wait time in minutes"""
        try:
            # Simple calculation: assume 5 minutes per conversation ahead
            base_time = position * 5
            
            # Adjust based on available agents
            active_agents = self.db.query(AgentSession).join(Agent).filter(
                Agent.tenant_id == tenant_id,
                AgentSession.logout_at.is_(None),
                AgentSession.is_accepting_chats == True
            ).count()
            
            if active_agents > 0:
                base_time = max(1, base_time // active_agents)
            
            return min(base_time, 60)  # Cap at 60 minutes
            
        except Exception as e:
            logger.error(f"Error calculating wait time: {str(e)}")
            return position * 5

    def assign_conversation(self, queue_id: int, agent_id: int, method: str = "manual") -> bool:
        """Assign conversation from queue to agent"""
        try:
            # Get queue entry
            queue_entry = self.db.query(ChatQueue).filter(
                ChatQueue.id == queue_id,
                ChatQueue.status == "waiting"
            ).first()
            
            if not queue_entry:
                return False
            
            # Get conversation
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == queue_entry.conversation_id
            ).first()
            
            if not conversation:
                return False
            
            # Use timezone-aware datetime
            current_time = datetime.now(timezone.utc)
            
            # Update queue entry
            queue_entry.status = "assigned"
            queue_entry.assigned_at = current_time
            queue_entry.assigned_agent_id = agent_id
            queue_entry.assignment_method = method
            
            # Update conversation
            conversation.status = ConversationStatus.ASSIGNED
            conversation.assigned_agent_id = agent_id
            conversation.assigned_at = current_time
            conversation.assignment_method = method
            
            # Calculate wait time - make both datetime objects timezone-aware
            if conversation.queue_entry_time:
                if conversation.queue_entry_time.tzinfo is None:
                    queue_time = conversation.queue_entry_time.replace(tzinfo=timezone.utc)
                else:
                    queue_time = conversation.queue_entry_time
                
                wait_seconds = (current_time - queue_time).total_seconds()
                conversation.wait_time_seconds = int(wait_seconds)
            
            # Update agent session
            agent_session = self.db.query(AgentSession).filter(
                AgentSession.agent_id == agent_id,
                AgentSession.logout_at.is_(None)
            ).first()
            
            if agent_session:
                agent_session.active_conversations += 1
            
            self.db.commit()
            
            logger.info(f"Conversation {conversation.id} assigned to agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error assigning conversation: {str(e)}")
            self.db.rollback()
            return False





    
    async def add_to_queue_with_smart_routing(self, conversation_id: int, priority: int = 1,
                                            preferred_agent_id: int = None, 
                                            assignment_criteria: Dict = None) -> Dict:
        """
        Add conversation to queue with intelligent routing analysis
        """
        try:
            # Get conversation details
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            # Keep priority as integer - don't convert to string
            if not isinstance(priority, int):
                priority = 1  # Default to normal priority
            
            # Create queue entry directly
            max_position = self.db.query(func.max(ChatQueue.position)).filter(
                ChatQueue.tenant_id == conversation.tenant_id,
                ChatQueue.status == "waiting"
            ).scalar()
            
            next_position = (max_position or 0) + 1
            
            queue_entry = ChatQueue(
                conversation_id=conversation_id,
                tenant_id=conversation.tenant_id,
                priority=priority,
                status="waiting",
                preferred_agent_id=preferred_agent_id,
                assignment_criteria=json.dumps(assignment_criteria) if assignment_criteria else None,
                queued_at=datetime.utcnow(),
                position=next_position
            )
            
            self.db.add(queue_entry)
            
            # Update conversation
            conversation.status = ConversationStatus.QUEUED
            conversation.queue_entry_time = datetime.utcnow()
            conversation.queue_position = queue_entry.position
            
            self.db.commit()
            self.db.refresh(queue_entry)
            
            queue_result = {
                "success": True,
                "queue_id": queue_entry.id,
                "position": queue_entry.position,
                "estimated_wait_time": next_position * 5
            }
            
            # Try intelligent routing
            routing_result = await self.smart_routing.find_best_agent(conversation_id)
            
            if routing_result.get("success") and routing_result.get("agent_id"):
                # Smart routing found a good match - store as suggestion
                best_agent_id = routing_result["agent_id"]
                
                logger.info(f"Smart routing suggests agent {best_agent_id} for conversation {conversation_id}")
                
                # Check if the suggested agent is actually available
                if await self._verify_agent_availability(best_agent_id, conversation.tenant_id):
                    # Get the queue entry that was just created
                    queue_entry = self.db.query(ChatQueue).filter(
                        ChatQueue.conversation_id == conversation_id,
                        ChatQueue.status == "waiting"
                    ).first()
                    
                    if queue_entry:
                        # Store suggestion instead of auto-assigning
                        queue_entry.suggested_agent_id = best_agent_id
                        queue_entry.suggestion_confidence = routing_result.get("confidence", 0.0)
                        queue_entry.status = "suggested"
                        self.db.commit()
                        
                        queue_result.update({
                            "immediately_assigned": False,
                            "smart_routing_available": True,
                            "suggested_agent_id": best_agent_id,
                            "routing_method": "smart_tags",
                            "routing_confidence": routing_result.get("confidence", 0.0),
                            "detected_tags": routing_result.get("detected_tags", []),
                            "routing_reasoning": routing_result.get("reasoning", []),
                            "estimated_wait_time": self._calculate_smart_wait_time(
                                conversation.tenant_id, queue_result.get("position", 1), best_agent_id
                            )
                        })
                        
                        logger.info(f"Conversation {conversation_id} suggested for agent {best_agent_id}")
                    else:
                        logger.warning(f"Queue entry not found for conversation {conversation_id}")
                else:
                    logger.info(f"Suggested agent {best_agent_id} not available, keeping in queue")
                    queue_result.update({
                        "immediately_assigned": False,
                        "smart_routing_available": True,
                        "suggested_agent_unavailable": True,
                        "routing_confidence": routing_result.get("confidence", 0.0)
                    })
            else:
                # Smart routing didn't find a good match or failed
                logger.info(f"Smart routing failed or no good match for conversation {conversation_id}")
                queue_result.update({
                    "immediately_assigned": False,
                    "smart_routing_available": False,
                    "routing_error": routing_result.get("error"),
                    "fallback_method": "traditional_queue"
                })
            
            return queue_result
            
        except Exception as e:
            logger.error(f"Error in enhanced queue service: {str(e)}")
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    async def _verify_agent_availability(self, agent_id: int, tenant_id: int) -> bool:
        """Verify that the suggested agent is actually available for assignment"""
        try:
            agent_session = self.db.query(AgentSession).filter(
                AgentSession.agent_id == agent_id,
                AgentSession.logout_at.is_(None),
                AgentSession.is_accepting_chats == True,
                AgentSession.active_conversations < AgentSession.max_concurrent_chats
            ).first()
            
            if not agent_session:
                return False
            
            # Verify agent belongs to the correct tenant
            agent = self.db.query(Agent).filter(
                Agent.id == agent_id,
                Agent.tenant_id == tenant_id,
                Agent.status == AgentStatus.ACTIVE,
                Agent.is_active == True
            ).first()
            
            return agent is not None
            
        except Exception as e:
            logger.error(f"Error verifying agent availability: {str(e)}")
            return False
    
    def _calculate_smart_wait_time(self, tenant_id: int, position: int, suggested_agent_id: int = None) -> int:
        """Calculate wait time considering smart routing predictions"""
        try:
            base_wait_time = self._calculate_wait_time(tenant_id, position)
            
            if suggested_agent_id:
                # Check suggested agent's current load
                agent_session = self.db.query(AgentSession).filter(
                    AgentSession.agent_id == suggested_agent_id,
                    AgentSession.logout_at.is_(None)
                ).first()
                
                if agent_session:
                    # If agent has low load, reduce wait time
                    load_factor = agent_session.active_conversations / agent_session.max_concurrent_chats
                    if load_factor < 0.5:
                        base_wait_time = max(1, int(base_wait_time * 0.7))  # 30% reduction
                    elif load_factor < 0.8:
                        base_wait_time = max(1, int(base_wait_time * 0.85))  # 15% reduction
            
            return base_wait_time
            
        except Exception as e:
            logger.error(f"Error calculating smart wait time: {str(e)}")
            return self._calculate_wait_time(tenant_id, position)
    
    async def smart_reassignment(self, tenant_id: int) -> Dict[str, Any]:
        """
        Periodically reassess queue and optimize assignments based on agent tags
        """
        try:
            # Get current queue
            waiting_queue = self.db.query(ChatQueue).join(LiveChatConversation).filter(
                ChatQueue.tenant_id == tenant_id,
                ChatQueue.status == "waiting"
            ).order_by(ChatQueue.priority.desc(), ChatQueue.position.asc()).all()
            
            if not waiting_queue:
                return {
                    "success": True,
                    "message": "No conversations in queue",
                    "reassignments": 0
                }
            
            # Get available agents
            available_agents = await self.smart_routing._get_available_agents(tenant_id)
            
            if not available_agents:
                return {
                    "success": True,
                    "message": "No agents available for reassignment",
                    "reassignments": 0
                }
            
            reassignments = []
            
            # Process each conversation in queue
            for queue_entry in waiting_queue:
                try:
                    conversation = queue_entry.conversation
                    
                    # Skip if conversation has been waiting less than 5 minutes
                    if queue_entry.queued_at:
                        wait_time = datetime.utcnow() - queue_entry.queued_at
                        if wait_time.total_seconds() < 300:  # 5 minutes
                            continue
                    
                    # Get smart routing recommendation
                    routing_result = await self.smart_routing.find_best_agent(conversation.id)
                    
                    if (routing_result.get("success") and 
                        routing_result.get("agent_id") and 
                        routing_result.get("confidence", 0) >= 0.7):  # High confidence only
                        
                        suggested_agent_id = routing_result["agent_id"]
                        
                        # Verify agent is still available
                        if await self._verify_agent_availability(suggested_agent_id, tenant_id):
                            # Attempt assignment
                            if self.assign_conversation(queue_entry.id, suggested_agent_id, "smart_reassignment"):
                                reassignments.append({
                                    "conversation_id": conversation.id,
                                    "queue_id": queue_entry.id,
                                    "agent_id": suggested_agent_id,
                                    "confidence": routing_result.get("confidence"),
                                    "wait_time_minutes": int(wait_time.total_seconds() / 60) if queue_entry.queued_at else 0,
                                    "detected_tags": [tag.get("tag_name") for tag in routing_result.get("detected_tags", [])]
                                })
                                
                                logger.info(f"Smart reassignment: conversation {conversation.id} to agent {suggested_agent_id}")
                
                except Exception as e:
                    logger.error(f"Error processing queue entry {queue_entry.id}: {str(e)}")
                    continue
            
            return {
                "success": True,
                "message": f"Smart reassignment completed",
                "reassignments": len(reassignments),
                "details": reassignments,
                "processed_conversations": len(waiting_queue)
            }
            
        except Exception as e:
            logger.error(f"Error in smart reassignment: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def get_enhanced_queue_status(self, tenant_id: int) -> Dict:
        """Get queue status with smart routing insights"""
        try:
            # Get base queue status
            base_status = self.get_queue_status(tenant_id)
            
            if "error" in base_status:
                return base_status
            
            # Add smart routing insights
            enhanced_queue = []
            
            for queue_item in base_status.get("queue", []):
                conversation_id = queue_item["conversation_id"]
                
                # Get conversation tags
                conversation_tags = self.db.query(ConversationTagging).join(AgentTag).filter(
                    ConversationTagging.conversation_id == conversation_id
                ).all()
                
                # Get routing recommendation
                try:
                    routing_result = await self.smart_routing.find_best_agent(conversation_id)
                    
                    enhanced_item = {
                        **queue_item,
                        "detected_tags": [
                            {
                                "name": tag.tag.name,
                                "display_name": tag.tag.display_name,
                                "confidence": tag.confidence_score,
                                "category": tag.tag.category
                            } for tag in conversation_tags
                        ],
                        "routing_suggestion": {
                            "has_suggestion": routing_result.get("success", False),
                            "agent_id": routing_result.get("agent_id"),
                            "confidence": routing_result.get("confidence", 0.0),
                            "reasoning": routing_result.get("reasoning", [])[:3],  # Top 3 reasons
                            "method": routing_result.get("routing_method", "unknown")
                        },
                        "priority_indicators": self._get_priority_indicators(conversation_id)
                    }
                    
                except Exception as e:
                    logger.error(f"Error getting routing suggestion for conversation {conversation_id}: {str(e)}")
                    enhanced_item = {
                        **queue_item,
                        "detected_tags": [],
                        "routing_suggestion": {"has_suggestion": False, "error": str(e)},
                        "priority_indicators": []
                    }
                
                enhanced_queue.append(enhanced_item)
            
            # Add smart routing statistics
            routing_stats = await self._get_routing_statistics(tenant_id)
            
            base_status.update({
                "enhanced_queue": enhanced_queue,
                "smart_routing_stats": routing_stats,
                "capabilities": {
                    "smart_routing_enabled": True,
                    "tag_based_routing": True,
                    "auto_reassignment": True
                }
            })
            
            return base_status
            
        except Exception as e:
            logger.error(f"Error getting enhanced queue status: {str(e)}")
            return {"error": str(e)}
    
    def _get_priority_indicators(self, conversation_id: int) -> List[str]:
        """Get priority indicators for a conversation"""
        indicators = []
        
        try:
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            if not conversation:
                return indicators
            
            # Check wait time
            if conversation.queue_entry_time:
                wait_minutes = (datetime.utcnow() - conversation.queue_entry_time).total_seconds() / 60
                if wait_minutes > 20:
                    indicators.append("long_wait")
                elif wait_minutes > 10:
                    indicators.append("moderate_wait")
            
            # Check for urgency keywords in original message
            if conversation.original_question:
                urgency_keywords = ["urgent", "emergency", "critical", "broken", "not working"]
                message_lower = conversation.original_question.lower()
                
                for keyword in urgency_keywords:
                    if keyword in message_lower:
                        indicators.append("urgent_keywords")
                        break
            
            # Check customer history
            if conversation.customer_identifier:
                recent_abandoned = self.db.query(LiveChatConversation).filter(
                    and_(
                        LiveChatConversation.tenant_id == conversation.tenant_id,
                        LiveChatConversation.customer_identifier == conversation.customer_identifier,
                        LiveChatConversation.status == ConversationStatus.ABANDONED,
                        LiveChatConversation.created_at >= datetime.utcnow() - timedelta(days=7)
                    )
                ).count()
                
                if recent_abandoned > 0:
                    indicators.append("abandonment_risk")
            
            # Check for high-value customer indicators
            conversation_tags = self.db.query(ConversationTagging).join(AgentTag).filter(
                and_(
                    ConversationTagging.conversation_id == conversation_id,
                    AgentTag.category.in_(["billing", "sales", "enterprise"])
                )
            ).count()
            
            if conversation_tags > 0:
                indicators.append("high_value")
            
        except Exception as e:
            logger.error(f"Error getting priority indicators: {str(e)}")
        
        return indicators
    
    async def _get_routing_statistics(self, tenant_id: int) -> Dict[str, Any]:
        """Get routing performance statistics"""
        try:
            # Get statistics for last 24 hours
            since = datetime.utcnow() - timedelta(hours=24)
            
            routing_logs = self.db.query(SmartRoutingLog).filter(
                and_(
                    SmartRoutingLog.tenant_id == tenant_id,
                    SmartRoutingLog.routed_at >= since
                )
            ).all()
            
            if not routing_logs:
                return {
                    "period": "24_hours",
                    "total_routes": 0,
                    "smart_routes": 0,
                    "success_rate": 0.0,
                    "avg_confidence": 0.0
                }
            
            total_routes = len(routing_logs)
            smart_routes = len([log for log in routing_logs if log.routing_method == "smart_tags"])
            
            # Calculate success metrics
            completed_conversations = [
                log for log in routing_logs 
                if log.customer_satisfaction is not None
            ]
            
            avg_satisfaction = 0.0
            if completed_conversations:
                avg_satisfaction = sum(
                    log.customer_satisfaction for log in completed_conversations
                ) / len(completed_conversations)
            
            avg_confidence = sum(log.confidence_score for log in routing_logs) / total_routes
            
            # Tag effectiveness
            tag_usage = {}
            for log in routing_logs:
                if log.detected_tags:
                    for tag_data in log.detected_tags:
                        tag_name = tag_data.get("tag_name", "unknown")
                        if tag_name not in tag_usage:
                            tag_usage[tag_name] = 0
                        tag_usage[tag_name] += 1
            
            return {
                "period": "24_hours",
                "total_routes": total_routes,
                "smart_routes": smart_routes,
                "smart_routing_percentage": round((smart_routes / total_routes) * 100, 1),
                "avg_confidence": round(avg_confidence, 3),
                "avg_satisfaction": round(avg_satisfaction, 2),
                "completed_conversations": len(completed_conversations),
                "most_used_tags": sorted(
                    tag_usage.items(), 
                    key=lambda x: x[1], 
                    reverse=True
                )[:5]
            }
            
        except Exception as e:
            logger.error(f"Error getting routing statistics: {str(e)}")
            return {"error": str(e)}
    
    async def get_agent_workload_optimization(self, tenant_id: int) -> Dict[str, Any]:
        """Analyze and suggest workload optimization based on agent tags"""
        try:
            # Get all active agents with their tags and current load
            agents_data = await self.smart_routing._get_available_agents(tenant_id)
            
            # Get current queue with tag analysis
            waiting_queue = self.db.query(ChatQueue).join(LiveChatConversation).filter(
                ChatQueue.tenant_id == tenant_id,
                ChatQueue.status == "waiting"
            ).all()
            
            # Analyze queue demand by tag category
            queue_demand = {}
            for queue_entry in waiting_queue:
                conversation_tags = self.db.query(ConversationTagging).join(AgentTag).filter(
                    ConversationTagging.conversation_id == queue_entry.conversation_id
                ).all()
                
                for tag_record in conversation_tags:
                    category = tag_record.tag.category
                    if category not in queue_demand:
                        queue_demand[category] = 0
                    queue_demand[category] += 1
            
            # Analyze agent capacity by category
            agent_capacity = {}
            agent_utilization = []
            
            for agent in agents_data:
                agent_categories = set()
                
                for tag in agent["tags"]:
                    category = tag["category"]
                    agent_categories.add(category)
                    
                    if category not in agent_capacity:
                        agent_capacity[category] = {"agents": 0, "total_capacity": 0, "current_load": 0}
                    
                    # Add agent capacity for this category
                    tag_capacity = tag.get("max_concurrent", 2)
                    agent_capacity[category]["total_capacity"] += tag_capacity
                    agent_capacity[category]["current_load"] += agent["current_load"]
                
                # Count unique agents per category
                for category in agent_categories:
                    agent_capacity[category]["agents"] += 1
                
                # Calculate individual agent utilization
                max_capacity = agent["max_capacity"]
                utilization = (agent["current_load"] / max_capacity) * 100 if max_capacity > 0 else 0
                
                agent_utilization.append({
                    "agent_id": agent["agent_id"],
                    "agent_name": agent["display_name"],
                    "current_load": agent["current_load"],
                    "max_capacity": max_capacity,
                    "utilization_percent": round(utilization, 1),
                    "specializations": agent["specializations"],
                    "can_take_more": agent["current_load"] < max_capacity
                })
            
            # Identify bottlenecks and opportunities
            bottlenecks = []
            opportunities = []
            
            for category, demand in queue_demand.items():
                capacity_info = agent_capacity.get(category, {"agents": 0, "total_capacity": 0})
                
                if capacity_info["agents"] == 0:
                    bottlenecks.append({
                        "category": category,
                        "issue": "no_specialized_agents",
                        "demand": demand,
                        "suggestion": f"Train agents in {category} skills or hire specialist"
                    })
                elif demand > capacity_info["total_capacity"]:
                    bottlenecks.append({
                        "category": category,
                        "issue": "insufficient_capacity",
                        "demand": demand,
                        "capacity": capacity_info["total_capacity"],
                        "suggestion": f"Increase {category} capacity or improve efficiency"
                    })
            
            # Find underutilized agents who could help
            underutilized = [
                agent for agent in agent_utilization 
                if agent["utilization_percent"] < 50 and agent["can_take_more"]
            ]
            
            if underutilized:
                opportunities.append({
                    "type": "underutilized_agents",
                    "agents": underutilized,
                    "suggestion": "Consider cross-training these agents for high-demand categories"
                })
            
            return {
                "success": True,
                "analysis_timestamp": datetime.utcnow().isoformat(),
                "queue_demand": queue_demand,
                "agent_capacity": agent_capacity,
                "agent_utilization": sorted(agent_utilization, key=lambda x: x["utilization_percent"], reverse=True),
                "bottlenecks": bottlenecks,
                "opportunities": opportunities,
                "recommendations": self._generate_optimization_recommendations(
                    queue_demand, agent_capacity, agent_utilization
                )
            }
            
        except Exception as e:
            logger.error(f"Error analyzing workload optimization: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _generate_optimization_recommendations(self, queue_demand: Dict, 
                                            agent_capacity: Dict, 
                                            agent_utilization: List) -> List[Dict]:
        """Generate actionable optimization recommendations"""
        recommendations = []
        
        try:
            # Check for high-demand categories with low capacity
            for category, demand in queue_demand.items():
                capacity_info = agent_capacity.get(category, {"agents": 0, "total_capacity": 0})
                
                if demand > 0 and capacity_info["agents"] < 2:
                    recommendations.append({
                        "priority": "high",
                        "type": "staffing",
                        "category": category,
                        "action": f"Assign more agents to {category} category",
                        "impact": "Reduce wait times for this category",
                        "current_agents": capacity_info["agents"],
                        "recommended_agents": max(2, capacity_info["agents"] + 1)
                    })
            
            # Check for overall utilization balance
            high_util_agents = [a for a in agent_utilization if a["utilization_percent"] > 80]
            low_util_agents = [a for a in agent_utilization if a["utilization_percent"] < 30]
            
            if high_util_agents and low_util_agents:
                recommendations.append({
                    "priority": "medium",
                    "type": "load_balancing",
                    "action": "Redistribute workload between agents",
                    "impact": "Better utilization and reduced burnout",
                    "overloaded_agents": len(high_util_agents),
                    "underutilized_agents": len(low_util_agents)
                })
            
            # Suggest cross-training opportunities
            if low_util_agents:
                high_demand_categories = sorted(queue_demand.items(), key=lambda x: x[1], reverse=True)[:3]
                
                for category, demand in high_demand_categories:
                    if demand > 0:
                        recommendations.append({
                            "priority": "low",
                            "type": "training",
                            "action": f"Cross-train underutilized agents in {category}",
                            "impact": "Increase flexibility and reduce bottlenecks",
                            "category": category,
                            "available_agents": [a["agent_name"] for a in low_util_agents[:3]]
                        })
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {str(e)}")
        
        return recommendations
    


    def transfer_conversation(self, conversation_id: int, from_agent_id: int, 
                            to_agent_id: int, reason: str = "transfer") -> bool:
        """Transfer conversation from one agent to another"""
        try:
            conversation = self.db.query(LiveChatConversation).filter(
                LiveChatConversation.id == conversation_id
            ).first()
            
            if not conversation:
                return False
            
            # Update conversation
            conversation.previous_agent_id = from_agent_id
            conversation.assigned_agent_id = to_agent_id
            conversation.status = ConversationStatus.TRANSFERRED
            conversation.assignment_method = "transfer"
            
            # Update agent sessions
            if from_agent_id:
                from_session = self.db.query(AgentSession).filter(
                    AgentSession.agent_id == from_agent_id,
                    AgentSession.logout_at.is_(None)
                ).first()
                if from_session:
                    from_session.active_conversations = max(0, from_session.active_conversations - 1)
            
            to_session = self.db.query(AgentSession).filter(
                AgentSession.agent_id == to_agent_id,
                AgentSession.logout_at.is_(None)
            ).first()
            if to_session:
                to_session.active_conversations += 1
            
            self.db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error transferring conversation: {str(e)}")
            self.db.rollback()
            return False