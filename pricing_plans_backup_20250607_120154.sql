-- Pricing Plans Backup
-- Created: 2025-06-07 12:01:54.259244

-- Plan: Free
UPDATE pricing_plans SET price_monthly = 0, price_yearly = 0, max_messages_monthly = 50 WHERE plan_type = 'free';

