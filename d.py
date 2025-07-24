def create_default_plans(self):
    """Create or update default pricing plans"""
    print("🔥 UPDATING PLANS WITH NEW FEATURES")
    
    plans = [
        {
            "name": "Free",
            "plan_type": "free",
            "price_monthly": 0.00,
            "price_yearly": 0.00,
            "max_integrations": -1,  # Unlimited integrations
            "max_messages_monthly": 50,  # 50 conversations
            "custom_prompt_allowed": True,
            "website_api_allowed": True,
            "slack_allowed": False,
            "discord_allowed": True,
            "whatsapp_allowed": False,  # Temporarily removed
            "features": '["50 Conversations", "Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Bot Memory"]',
            "is_active": True,
            "is_addon": False,
            "is_popular": False,
            "display_order": 1
        },
        {
            "name": "Basic",
            "plan_type": "basic",
            "price_monthly": 9.99,  # UPDATED PRICE
            "price_yearly": 99.00,  # UPDATED PRICE
            "max_integrations": -1,  # Unlimited integrations
            "max_messages_monthly": 2000,  # UPDATED: 2,000 conversations
            "custom_prompt_allowed": True,
            "website_api_allowed": True,
            "slack_allowed": True,
            "discord_allowed": True,
            "whatsapp_allowed": False,  # Temporarily removed
            "features": '["2000 conversations", "Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Bot Memory"]',
            "is_active": True,
            "is_addon": False,
            "is_popular": False,
            "display_order": 2
        },
        {
            "name": "Growth",
            "plan_type": "growth",
            "price_monthly": 29.00,  # UPDATED PRICE
            "price_yearly": 290.00,  # UPDATED PRICE
            "max_integrations": -1,  # Unlimited integrations
            "max_messages_monthly": 5000,  # 5,000 conversations
            "custom_prompt_allowed": True,
            "website_api_allowed": True,
            "slack_allowed": True,
            "discord_allowed": True,
            "whatsapp_allowed": False,  # Temporarily removed
            "features": '["5000 conversations", "Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Bot Memory"]',
            "is_active": True,
            "is_addon": False,
            "is_popular": True,  # Popular plan
            "display_order": 3
        },
        {
            "name": "Pro",  # NEW PLAN
            "plan_type": "pro",
            "price_monthly": 59.00,
            "price_yearly": 590.00,
            "max_integrations": -1,  # Unlimited integrations
            "max_messages_monthly": 20000,  # 20,000 conversations
            "custom_prompt_allowed": True,
            "website_api_allowed": True,
            "slack_allowed": True,
            "discord_allowed": True,
            "whatsapp_allowed": False,  
            "features": '["20,000  Conversations", "Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Enhanced Bot Memory", "API Access"]',
            "is_active": True,
            "is_addon": False,
            "is_popular": False,
            "display_order": 4
        },
        {
            "name": "Agency", 
            "plan_type": "agency",
            "price_monthly": 99.00,
            "price_yearly": 990.00,
            "max_integrations": -1,  # Unlimited integrations
            "max_messages_monthly": 50000,  # 50,000 conversations
            "custom_prompt_allowed": True,
            "website_api_allowed": True,
            "slack_allowed": True,
            "discord_allowed": True,
            "whatsapp_allowed": False,  # Temporarily removed
            "features": '["Unlimited Conversations", "Custom Prompt", "Slack Integration", "Discord Integration", "Web Integration", "Advanced Analytics", "Priority Support", "Enhanced Bot Memory", "API Access", "White Label", "Custom Integrations"]',
            "is_active": True,
            "is_addon": False,
            "is_popular": False,
            "display_order": 5
        }
    ]
    
    for plan_data in plans:
        # Check if plan exists by plan_type
        existing_plan = self.db.query(PricingPlan).filter(
            PricingPlan.plan_type == plan_data["plan_type"]
        ).first()
        
        if existing_plan:
            # Update existing plan
            for key, value in plan_data.items():
                setattr(existing_plan, key, value)
        else:
            # Create new plan
            plan = PricingPlan(**plan_data)
            self.db.add(plan)
    
    self.db.commit()