-- Render Database Backup
-- Created: 2025-06-07 12:19:15.932605

-- Plan: Free
UPDATE pricing_plans SET price_monthly = 0.00, price_yearly = 0.00, max_messages_monthly = 50 WHERE plan_type = 'free';

