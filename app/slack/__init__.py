# app/slack/__init__.py
"""
Slack Integration Module for Multi-Tenant Chatbot
"""

from .bot_manager import SlackBotManager, get_slack_bot_manager
from .router import router

__all__ = ["SlackBotManager", "get_slack_bot_manager", "router"]