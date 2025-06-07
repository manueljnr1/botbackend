-- Pricing Plans Backup
-- Created: 2025-06-07 12:11:11.716691

-- Plan: Basic
UPDATE pricing_plans SET price_monthly = 9.99, price_yearly = 99, max_messages_monthly = 2000 WHERE plan_type = 'basic';

-- Plan: Growth
UPDATE pricing_plans SET price_monthly = 29, price_yearly = 290, max_messages_monthly = 5000 WHERE plan_type = 'growth';

-- Plan: Agency
UPDATE pricing_plans SET price_monthly = 99, price_yearly = 990, max_messages_monthly = 50000 WHERE plan_type = 'agency';

-- Plan: Free
UPDATE pricing_plans SET price_monthly = 0, price_yearly = 0, max_messages_monthly = 50 WHERE plan_type = 'free';

-- Plan: Pro
UPDATE pricing_plans SET price_monthly = 59, price_yearly = 590, max_messages_monthly = 20000 WHERE plan_type = 'pro';

