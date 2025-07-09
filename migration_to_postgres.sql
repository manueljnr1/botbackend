-- SQLite to PostgreSQL Migration Script
-- Generated automatically
-- Review and test before running on production!

-- Enable UUID extension (common in Supabase)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table: admins
DROP TABLE IF EXISTS admins CASCADE;
CREATE TABLE admins (
	id INTEGER NOT NULL, 
	username VARCHAR NOT NULL, 
	email VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	hashed_password VARCHAR NOT NULL, 
	is_active BOOLEAN, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id)
);

-- Indexes for admins
CREATE UNIQUE INDEX ix_admins_email ON admins (email);
CREATE INDEX ix_admins_id ON admins (id);
CREATE UNIQUE INDEX ix_admins_username ON admins (username);

-- Table: agent_permission_overrides
DROP TABLE IF EXISTS agent_permission_overrides CASCADE;
CREATE TABLE agent_permission_overrides (
	id INTEGER NOT NULL, 
	agent_id INTEGER NOT NULL, 
	permission VARCHAR NOT NULL, 
	granted BOOLEAN, 
	granted_by INTEGER, 
	granted_at TIMESTAMP, 
	reason TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT unique_agent_permission UNIQUE (agent_id, permission), 
	FOREIGN KEY(agent_id) REFERENCES agents (id), 
	FOREIGN KEY(granted_by) REFERENCES agents (id)
);

-- Indexes for agent_permission_overrides
CREATE INDEX ix_agent_permission_overrides_id ON agent_permission_overrides (id);

-- Table: agent_role_history
DROP TABLE IF EXISTS agent_role_history CASCADE;
CREATE TABLE agent_role_history (
	id INTEGER NOT NULL, 
	agent_id INTEGER NOT NULL, 
	old_role VARCHAR, 
	new_role VARCHAR NOT NULL, 
	changed_by INTEGER, 
	changed_at TIMESTAMP, 
	reason TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(agent_id) REFERENCES agents (id), 
	FOREIGN KEY(changed_by) REFERENCES agents (id)
);

-- Indexes for agent_role_history
CREATE INDEX ix_agent_role_history_id ON agent_role_history (id);

-- Table: agent_sessions
DROP TABLE IF EXISTS agent_sessions CASCADE;
CREATE TABLE agent_sessions (
	id INTEGER NOT NULL, 
	agent_id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	session_id VARCHAR NOT NULL, 
	status VARCHAR, 
	login_at TIMESTAMP, 
	logout_at TIMESTAMP, 
	last_activity TIMESTAMP, 
	active_conversations INTEGER, 
	max_concurrent_chats INTEGER, 
	is_accepting_chats BOOLEAN, 
	messages_sent INTEGER, 
	conversations_handled INTEGER, 
	average_response_time FLOAT, 
	total_online_time INTEGER, 
	ip_address VARCHAR, 
	user_agent VARCHAR, 
	websocket_id VARCHAR, 
	device_type VARCHAR, 
	browser VARCHAR, 
	status_message VARCHAR, 
	away_message VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(agent_id) REFERENCES agents (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	UNIQUE (websocket_id)
);

-- Indexes for agent_sessions
CREATE INDEX ix_agent_sessions_id ON agent_sessions (id);
CREATE UNIQUE INDEX ix_agent_sessions_session_id ON agent_sessions (session_id);

-- Table: agent_tag_performance
DROP TABLE IF EXISTS agent_tag_performance CASCADE;
CREATE TABLE agent_tag_performance (
	id INTEGER NOT NULL, 
	agent_id INTEGER NOT NULL, 
	tag_id INTEGER NOT NULL, 
	total_conversations INTEGER, 
	successful_resolutions INTEGER, 
	average_resolution_time FLOAT, 
	customer_satisfaction_avg FLOAT, 
	conversations_last_30_days INTEGER, 
	satisfaction_last_30_days FLOAT, 
	proficiency_level INTEGER, 
	improvement_trend FLOAT, 
	certified BOOLEAN, 
	certification_date TIMESTAMP, 
	last_training_date TIMESTAMP, 
	is_available_for_tag BOOLEAN, 
	max_concurrent_for_tag INTEGER, 
	current_active_conversations INTEGER, 
	last_updated TIMESTAMP, 
	last_conversation_date TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(agent_id) REFERENCES agents (id), 
	FOREIGN KEY(tag_id) REFERENCES agent_tags (id)
);

-- Indexes for agent_tag_performance
CREATE INDEX ix_agent_tag_performance_id ON agent_tag_performance (id);

-- Table: agent_tags
DROP TABLE IF EXISTS agent_tags CASCADE;
CREATE TABLE agent_tags (
	id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	name VARCHAR(50) NOT NULL, 
	display_name VARCHAR(100) NOT NULL, 
	category VARCHAR(50) NOT NULL, 
	description TEXT, 
	color VARCHAR(7), 
	icon VARCHAR(50), 
	priority_weight FLOAT, 
	is_active BOOLEAN, 
	keywords JSON, 
	routing_rules JSON, 
	total_conversations INTEGER, 
	success_rate FLOAT, 
	average_satisfaction FLOAT, 
	created_by INTEGER, 
	created_at TIMESTAMP, 
	updated_at TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(created_by) REFERENCES agents (id)
);

-- Indexes for agent_tags
CREATE INDEX ix_agent_tags_category ON agent_tags (category);
CREATE INDEX ix_agent_tags_id ON agent_tags (id);
CREATE INDEX ix_agent_tags_name ON agent_tags (name);

-- Table: agent_tags_association
DROP TABLE IF EXISTS agent_tags_association CASCADE;
CREATE TABLE agent_tags_association (
	agent_id INTEGER NOT NULL, 
	tag_id INTEGER NOT NULL, 
	proficiency_level INTEGER, 
	assigned_at TIMESTAMP, 
	assigned_by INTEGER, 
	PRIMARY KEY (agent_id, tag_id), 
	FOREIGN KEY(agent_id) REFERENCES agents (id), 
	FOREIGN KEY(tag_id) REFERENCES agent_tags (id), 
	FOREIGN KEY(assigned_by) REFERENCES agents (id)
);

-- Table: agents
DROP TABLE IF EXISTS agents CASCADE;
CREATE TABLE agents (
	id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	email VARCHAR NOT NULL, 
	full_name VARCHAR NOT NULL, 
	display_name VARCHAR, 
	avatar_url VARCHAR, 
	password_hash VARCHAR, 
	invite_token VARCHAR, 
	invited_by INTEGER NOT NULL, 
	invited_at TIMESTAMP, 
	password_set_at TIMESTAMP, 
	status VARCHAR, 
	is_active BOOLEAN, 
	last_login TIMESTAMP, 
	last_seen TIMESTAMP, 
	is_online BOOLEAN, 
	total_conversations INTEGER, 
	total_messages_sent INTEGER, 
	average_response_time FLOAT, 
	customer_satisfaction_avg FLOAT, 
	conversations_today INTEGER, 
	notification_settings TEXT, 
	timezone VARCHAR, 
	max_concurrent_chats INTEGER, 
	auto_assign BOOLEAN, 
	work_hours_start VARCHAR, 
	work_hours_end VARCHAR, 
	work_days VARCHAR, 
	created_at TIMESTAMP, 
	updated_at TIMESTAMP, 
	role VARCHAR, 
	promoted_at TIMESTAMP, 
	promoted_by INTEGER, 
	can_assign_conversations BOOLEAN, 
	can_manage_team BOOLEAN, 
	can_access_analytics BOOLEAN, 
	primary_specialization VARCHAR(50), 
	secondary_specializations JSON, 
	skill_level INTEGER, 
	accepts_overflow BOOLEAN, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(invited_by) REFERENCES tenants (id), 
	FOREIGN KEY(promoted_by) REFERENCES agents (id)
);

-- Indexes for agents
CREATE INDEX ix_agents_email ON agents (email);
CREATE INDEX ix_agents_id ON agents (id);
CREATE UNIQUE INDEX ix_agents_invite_token ON agents (invite_token);

-- Table: billing_history
DROP TABLE IF EXISTS billing_history CASCADE;
CREATE TABLE billing_history (
	id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	subscription_id INTEGER NOT NULL, 
	amount NUMERIC(10, 2) NOT NULL, 
	currency VARCHAR, 
	billing_period_start TIMESTAMP NOT NULL, 
	billing_period_end TIMESTAMP NOT NULL, 
	plan_name VARCHAR, 
	conversations_included INTEGER, 
	conversations_used INTEGER, 
	addons_included TEXT, 
	stripe_invoice_id VARCHAR, 
	stripe_charge_id VARCHAR, 
	payment_status VARCHAR, 
	payment_date TIMESTAMP, 
	payment_method VARCHAR, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(subscription_id) REFERENCES tenant_subscriptions (id)
);

-- Indexes for billing_history
CREATE INDEX ix_billing_history_id ON billing_history (id);

-- Table: booking_requests
DROP TABLE IF EXISTS booking_requests CASCADE;
CREATE TABLE booking_requests (
	id INTEGER NOT NULL, 
	tenant_id INTEGER, 
	session_id VARCHAR, 
	user_identifier VARCHAR, 
	user_email VARCHAR, 
	user_name VARCHAR, 
	calendly_event_uri VARCHAR, 
	calendly_event_uuid VARCHAR, 
	booking_url VARCHAR, 
	status VARCHAR, 
	booking_message TEXT, 
	created_at TIMESTAMP, 
	booked_at TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(session_id) REFERENCES chat_sessions (session_id)
);

-- Indexes for booking_requests
CREATE INDEX ix_booking_requests_id ON booking_requests (id);

-- Table: chat_messages
DROP TABLE IF EXISTS chat_messages CASCADE;
CREATE TABLE chat_messages (
	id INTEGER NOT NULL, 
	session_id INTEGER, 
	content TEXT, 
	translated_content TEXT, 
	source_language VARCHAR(10), 
	target_language VARCHAR(10), 
	is_from_user BOOLEAN, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES chat_sessions (id)
);

-- Indexes for chat_messages
CREATE INDEX ix_chat_messages_id ON chat_messages (id);

-- Table: chat_queue
DROP TABLE IF EXISTS chat_queue CASCADE;
CREATE TABLE chat_queue (
	id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	conversation_id INTEGER NOT NULL, 
	position INTEGER NOT NULL, 
	priority INTEGER, 
	estimated_wait_time INTEGER, 
	preferred_agent_id INTEGER, 
	assignment_criteria TEXT, 
	skills_required TEXT, 
	language_preference VARCHAR, 
	entry_reason VARCHAR, 
	queue_source VARCHAR, 
	queued_at TIMESTAMP, 
	assigned_at TIMESTAMP, 
	removed_at TIMESTAMP, 
	status VARCHAR, 
	abandon_reason VARCHAR, 
	customer_message_preview TEXT, 
	urgency_indicators TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	UNIQUE (conversation_id), 
	FOREIGN KEY(conversation_id) REFERENCES live_chat_conversations (id), 
	FOREIGN KEY(preferred_agent_id) REFERENCES agents (id)
);

-- Indexes for chat_queue
CREATE INDEX ix_chat_queue_id ON chat_queue (id);
CREATE INDEX ix_chat_queue_position ON chat_queue (position);
CREATE INDEX ix_chat_queue_priority ON chat_queue (priority);

-- Table: chat_sessions
DROP TABLE IF EXISTS chat_sessions CASCADE;
CREATE TABLE chat_sessions (
	id INTEGER NOT NULL, 
	session_id VARCHAR, 
	tenant_id INTEGER, 
	user_identifier VARCHAR, 
	language_code VARCHAR(10), 
	is_active BOOLEAN, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP, 
	user_email VARCHAR, 
	email_captured_at TIMESTAMP, 
	email_expires_at TIMESTAMP, 
	discord_channel_id VARCHAR, 
	discord_user_id VARCHAR, 
	discord_guild_id VARCHAR, 
	platform VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

-- Indexes for chat_sessions
CREATE INDEX ix_chat_sessions_id ON chat_sessions (id);
CREATE UNIQUE INDEX ix_chat_sessions_session_id ON chat_sessions (session_id);
CREATE INDEX ix_chat_sessions_user_identifier ON chat_sessions (user_identifier);

-- Table: conversation_sessions
DROP TABLE IF EXISTS conversation_sessions CASCADE;
CREATE TABLE conversation_sessions (
	id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	user_identifier VARCHAR NOT NULL, 
	platform VARCHAR NOT NULL, 
	started_at TIMESTAMP NOT NULL, 
	last_activity TIMESTAMP NOT NULL, 
	is_active BOOLEAN, 
	message_count INTEGER, 
	duration_minutes INTEGER, 
	counted_for_billing BOOLEAN, 
	billing_period_start TIMESTAMP, 
	extra_data TEXT, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

-- Indexes for conversation_sessions
CREATE INDEX ix_conversation_sessions_id ON conversation_sessions (id);

-- Table: conversation_tagging
DROP TABLE IF EXISTS conversation_tagging CASCADE;
CREATE TABLE conversation_tagging (
	id INTEGER NOT NULL, 
	conversation_id INTEGER NOT NULL, 
	tag_id INTEGER NOT NULL, 
	confidence_score FLOAT, 
	detection_method VARCHAR(50) NOT NULL, 
	detected_keywords JSON, 
	message_text TEXT, 
	message_id INTEGER, 
	influenced_routing BOOLEAN, 
	routing_weight FLOAT, 
	human_verified BOOLEAN, 
	verified_by INTEGER, 
	verified_at TIMESTAMP, 
	detected_at TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(conversation_id) REFERENCES live_chat_conversations (id), 
	FOREIGN KEY(tag_id) REFERENCES agent_tags (id), 
	FOREIGN KEY(message_id) REFERENCES live_chat_messages (id), 
	FOREIGN KEY(verified_by) REFERENCES agents (id)
);

-- Indexes for conversation_tagging
CREATE INDEX ix_conversation_tagging_id ON conversation_tagging (id);

-- Table: conversation_tags
DROP TABLE IF EXISTS conversation_tags CASCADE;
CREATE TABLE conversation_tags (
	id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	color VARCHAR, 
	description VARCHAR, 
	usage_count INTEGER, 
	created_by_agent_id INTEGER, 
	created_at TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(created_by_agent_id) REFERENCES agents (id)
);

-- Indexes for conversation_tags
CREATE INDEX ix_conversation_tags_id ON conversation_tags (id);

-- Table: conversation_transfers
DROP TABLE IF EXISTS conversation_transfers CASCADE;
CREATE TABLE conversation_transfers (
	id INTEGER NOT NULL, 
	conversation_id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	from_agent_id INTEGER NOT NULL, 
	to_agent_id INTEGER, 
	transfer_reason VARCHAR, 
	transfer_notes TEXT, 
	status VARCHAR, 
	initiated_at TIMESTAMP, 
	completed_at TIMESTAMP, 
	conversation_summary TEXT, 
	customer_context TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(conversation_id) REFERENCES live_chat_conversations (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(from_agent_id) REFERENCES agents (id), 
	FOREIGN KEY(to_agent_id) REFERENCES agents (id)
);

-- Indexes for conversation_transfers
CREATE INDEX ix_conversation_transfers_id ON conversation_transfers (id);

-- Table: customer_devices
DROP TABLE IF EXISTS customer_devices CASCADE;
CREATE TABLE customer_devices (
	id INTEGER NOT NULL, 
	customer_profile_id INTEGER NOT NULL, 
	device_fingerprint VARCHAR NOT NULL, 
	device_type VARCHAR, 
	browser_name VARCHAR, 
	browser_version VARCHAR, 
	operating_system VARCHAR, 
	screen_resolution VARCHAR, 
	supports_websockets BOOLEAN, 
	supports_file_upload BOOLEAN, 
	supports_notifications BOOLEAN, 
	first_seen TIMESTAMP, 
	last_seen TIMESTAMP, 
	total_sessions INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_profile_id) REFERENCES customer_profiles (id)
);

-- Indexes for customer_devices
CREATE INDEX ix_customer_devices_device_fingerprint ON customer_devices (device_fingerprint);
CREATE INDEX ix_customer_devices_id ON customer_devices (id);

-- Table: customer_preferences
DROP TABLE IF EXISTS customer_preferences CASCADE;
CREATE TABLE customer_preferences (
	id INTEGER NOT NULL, 
	customer_profile_id INTEGER NOT NULL, 
	preferred_language VARCHAR, 
	preferred_agent_gender VARCHAR, 
	preferred_communication_style VARCHAR, 
	email_notifications BOOLEAN, 
	sms_notifications BOOLEAN, 
	browser_notifications BOOLEAN, 
	requires_accessibility_features BOOLEAN, 
	accessibility_preferences JSON, 
	data_retention_preference VARCHAR, 
	third_party_sharing_consent BOOLEAN, 
	created_at TIMESTAMP, 
	updated_at TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_profile_id) REFERENCES customer_profiles (id)
);

-- Indexes for customer_preferences
CREATE INDEX ix_customer_preferences_id ON customer_preferences (id);

-- Table: customer_profiles
DROP TABLE IF EXISTS customer_profiles CASCADE;
CREATE TABLE customer_profiles (
	id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	customer_identifier VARCHAR NOT NULL, 
	first_seen TIMESTAMP, 
	last_seen TIMESTAMP, 
	total_conversations INTEGER, 
	total_sessions INTEGER, 
	preferred_language VARCHAR, 
	time_zone VARCHAR, 
	preferred_contact_method VARCHAR, 
	customer_satisfaction_avg FLOAT, 
	average_session_duration INTEGER, 
	total_messages_sent INTEGER, 
	data_collection_consent BOOLEAN, 
	marketing_consent BOOLEAN, 
	last_consent_update TIMESTAMP, 
	created_at TIMESTAMP, 
	updated_at TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

-- Indexes for customer_profiles
CREATE INDEX ix_customer_profiles_customer_identifier ON customer_profiles (customer_identifier);
CREATE INDEX ix_customer_profiles_id ON customer_profiles (id);

-- Table: customer_sessions
DROP TABLE IF EXISTS customer_sessions CASCADE;
CREATE TABLE customer_sessions (
	id INTEGER NOT NULL, 
	customer_profile_id INTEGER NOT NULL, 
	session_id VARCHAR NOT NULL, 
	started_at TIMESTAMP, 
	ended_at TIMESTAMP, 
	duration_seconds INTEGER, 
	ip_address VARCHAR, 
	user_agent TEXT, 
	device_fingerprint VARCHAR, 
	country VARCHAR, 
	region VARCHAR, 
	city VARCHAR, 
	page_views INTEGER, 
	conversations_started INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_profile_id) REFERENCES customer_profiles (id), 
	UNIQUE (session_id)
);

-- Indexes for customer_sessions
CREATE INDEX ix_customer_sessions_id ON customer_sessions (id);

-- Table: faqs
DROP TABLE IF EXISTS faqs CASCADE;
CREATE TABLE faqs (
	id INTEGER NOT NULL, 
	tenant_id INTEGER, 
	question TEXT, 
	answer TEXT, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

-- Indexes for faqs
CREATE INDEX ix_faqs_id ON faqs (id);

-- Table: instagram_conversations
DROP TABLE IF EXISTS instagram_conversations CASCADE;
CREATE TABLE instagram_conversations (
	id INTEGER NOT NULL, 
	integration_id INTEGER, 
	tenant_id INTEGER, 
	instagram_user_id VARCHAR NOT NULL, 
	instagram_username VARCHAR, 
	user_profile_name VARCHAR, 
	user_profile_picture VARCHAR, 
	conversation_id VARCHAR, 
	thread_id VARCHAR, 
	is_active BOOLEAN, 
	conversation_status VARCHAR, 
	conversation_source VARCHAR, 
	initial_message_type VARCHAR, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP, 
	last_message_at TIMESTAMP, 
	last_user_message_at TIMESTAMP, 
	last_bot_message_at TIMESTAMP, 
	total_messages INTEGER, 
	user_messages INTEGER, 
	bot_messages INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(integration_id) REFERENCES instagram_integrations (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

-- Indexes for instagram_conversations
CREATE UNIQUE INDEX ix_instagram_conversations_conversation_id ON instagram_conversations (conversation_id);
CREATE INDEX ix_instagram_conversations_id ON instagram_conversations (id);
CREATE INDEX ix_instagram_conversations_instagram_user_id ON instagram_conversations (instagram_user_id);
CREATE INDEX ix_instagram_conversations_integration_id ON instagram_conversations (integration_id);
CREATE INDEX ix_instagram_conversations_tenant_id ON instagram_conversations (tenant_id);

-- Table: instagram_integrations
DROP TABLE IF EXISTS instagram_integrations CASCADE;
CREATE TABLE instagram_integrations (
	id INTEGER NOT NULL, 
	tenant_id INTEGER, 
	meta_app_id VARCHAR NOT NULL, 
	meta_app_secret VARCHAR NOT NULL, 
	instagram_business_account_id VARCHAR NOT NULL, 
	instagram_username VARCHAR NOT NULL, 
	facebook_page_id VARCHAR NOT NULL, 
	facebook_page_name VARCHAR, 
	page_access_token TEXT NOT NULL, 
	token_expires_at TIMESTAMP, 
	webhook_verify_token VARCHAR NOT NULL, 
	webhook_subscribed BOOLEAN, 
	webhook_subscription_fields JSON, 
	bot_enabled BOOLEAN, 
	bot_status VARCHAR, 
	auto_reply_enabled BOOLEAN, 
	business_verification_required BOOLEAN, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP, 
	last_message_at TIMESTAMP, 
	last_error TEXT, 
	error_count INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

-- Indexes for instagram_integrations
CREATE INDEX ix_instagram_integrations_facebook_page_id ON instagram_integrations (facebook_page_id);
CREATE INDEX ix_instagram_integrations_id ON instagram_integrations (id);
CREATE INDEX ix_instagram_integrations_instagram_business_account_id ON instagram_integrations (instagram_business_account_id);
CREATE UNIQUE INDEX ix_instagram_integrations_tenant_id ON instagram_integrations (tenant_id);

-- Table: instagram_messages
DROP TABLE IF EXISTS instagram_messages CASCADE;
CREATE TABLE instagram_messages (
	id INTEGER NOT NULL, 
	conversation_id INTEGER, 
	tenant_id INTEGER, 
	instagram_message_id VARCHAR, 
	message_uuid VARCHAR, 
	message_type VARCHAR, 
	content TEXT, 
	media_url VARCHAR, 
	media_type VARCHAR, 
	media_size INTEGER, 
	is_from_user BOOLEAN, 
	message_status VARCHAR, 
	reply_to_story BOOLEAN, 
	story_id VARCHAR, 
	quick_reply_payload VARCHAR, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	instagram_timestamp TIMESTAMP, 
	delivered_at TIMESTAMP, 
	read_at TIMESTAMP, 
	send_error TEXT, 
	retry_count INTEGER, 
	raw_webhook_data JSON, 
	PRIMARY KEY (id), 
	FOREIGN KEY(conversation_id) REFERENCES instagram_conversations (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

-- Indexes for instagram_messages
CREATE INDEX ix_instagram_messages_conversation_id ON instagram_messages (conversation_id);
CREATE INDEX ix_instagram_messages_id ON instagram_messages (id);
CREATE INDEX ix_instagram_messages_instagram_message_id ON instagram_messages (instagram_message_id);
CREATE UNIQUE INDEX ix_instagram_messages_message_uuid ON instagram_messages (message_uuid);
CREATE INDEX ix_instagram_messages_tenant_id ON instagram_messages (tenant_id);

-- Table: instagram_webhook_events
DROP TABLE IF EXISTS instagram_webhook_events CASCADE;
CREATE TABLE instagram_webhook_events (
	id INTEGER NOT NULL, 
	tenant_id INTEGER, 
	integration_id INTEGER, 
	event_type VARCHAR NOT NULL, 
	event_id VARCHAR, 
	instagram_user_id VARCHAR, 
	processing_status VARCHAR, 
	processing_error TEXT, 
	processed_at TIMESTAMP, 
	raw_payload JSON NOT NULL, 
	headers JSON, 
	received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	instagram_timestamp TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(integration_id) REFERENCES instagram_integrations (id)
);

-- Indexes for instagram_webhook_events
CREATE INDEX ix_instagram_webhook_events_event_id ON instagram_webhook_events (event_id);
CREATE INDEX ix_instagram_webhook_events_event_type ON instagram_webhook_events (event_type);
CREATE INDEX ix_instagram_webhook_events_id ON instagram_webhook_events (id);
CREATE INDEX ix_instagram_webhook_events_instagram_user_id ON instagram_webhook_events (instagram_user_id);
CREATE INDEX ix_instagram_webhook_events_integration_id ON instagram_webhook_events (integration_id);
CREATE INDEX ix_instagram_webhook_events_tenant_id ON instagram_webhook_events (tenant_id);

-- Table: knowledge_bases
DROP TABLE IF EXISTS knowledge_bases CASCADE;
CREATE TABLE knowledge_bases (
                id SERIAL PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                file_path TEXT,
                document_type TEXT NOT NULL,
                vector_store_id TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                processing_status TEXT DEFAULT 'pending',
                processing_error TEXT,
                processed_at TIMESTAMP,
                base_url TEXT,
                crawl_depth INTEGER DEFAULT 3,
                crawl_frequency_hours INTEGER DEFAULT 24,
                last_crawled_at TIMESTAMP,
                pages_crawled INTEGER DEFAULT 0,
                include_patterns TEXT,
                exclude_patterns TEXT,
                FOREIGN KEY (tenant_id) REFERENCES tenants (id)
            );

-- Table: live_chat_conversations
DROP TABLE IF EXISTS live_chat_conversations CASCADE;
CREATE TABLE live_chat_conversations (
	id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	customer_identifier VARCHAR NOT NULL, 
	customer_email VARCHAR, 
	customer_name VARCHAR, 
	customer_phone VARCHAR, 
	customer_ip VARCHAR, 
	customer_user_agent TEXT, 
	chatbot_session_id VARCHAR, 
	handoff_reason VARCHAR, 
	handoff_trigger VARCHAR, 
	handoff_context TEXT, 
	original_question TEXT, 
	status VARCHAR, 
	queue_position INTEGER, 
	priority_level INTEGER, 
	queue_entry_time TIMESTAMP, 
	assigned_agent_id INTEGER, 
	assigned_at TIMESTAMP, 
	assignment_method VARCHAR, 
	previous_agent_id INTEGER, 
	created_at TIMESTAMP, 
	first_response_at TIMESTAMP, 
	last_activity_at TIMESTAMP, 
	closed_at TIMESTAMP, 
	wait_time_seconds INTEGER, 
	response_time_seconds INTEGER, 
	conversation_duration_seconds INTEGER, 
	message_count INTEGER, 
	agent_message_count INTEGER, 
	customer_message_count INTEGER, 
	customer_satisfaction INTEGER, 
	customer_feedback TEXT, 
	satisfaction_submitted_at TIMESTAMP, 
	closed_by VARCHAR, 
	closure_reason VARCHAR, 
	resolution_status VARCHAR, 
	agent_notes TEXT, 
	internal_notes TEXT, 
	tags TEXT, 
	category VARCHAR, 
	department VARCHAR, 
	updated_at TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(assigned_agent_id) REFERENCES agents (id), 
	FOREIGN KEY(previous_agent_id) REFERENCES agents (id)
);

-- Indexes for live_chat_conversations
CREATE INDEX ix_live_chat_conversations_chatbot_session_id ON live_chat_conversations (chatbot_session_id);
CREATE INDEX ix_live_chat_conversations_customer_identifier ON live_chat_conversations (customer_identifier);
CREATE INDEX ix_live_chat_conversations_id ON live_chat_conversations (id);
CREATE INDEX ix_live_chat_conversations_status ON live_chat_conversations (status);

-- Table: live_chat_messages
DROP TABLE IF EXISTS live_chat_messages CASCADE;
CREATE TABLE live_chat_messages (
	id INTEGER NOT NULL, 
	conversation_id INTEGER NOT NULL, 
	content TEXT NOT NULL, 
	message_type VARCHAR, 
	raw_content TEXT, 
	sender_type VARCHAR NOT NULL, 
	sender_id VARCHAR, 
	agent_id INTEGER, 
	sender_name VARCHAR, 
	sender_avatar VARCHAR, 
	sent_at TIMESTAMP, 
	delivered_at TIMESTAMP, 
	read_at TIMESTAMP, 
	edited_at TIMESTAMP, 
	is_internal BOOLEAN, 
	is_edited BOOLEAN, 
	is_deleted BOOLEAN, 
	deleted_at TIMESTAMP, 
	attachment_url VARCHAR, 
	attachment_name VARCHAR, 
	attachment_type VARCHAR, 
	attachment_size INTEGER, 
	system_event_type VARCHAR, 
	system_event_data TEXT, 
	client_message_id VARCHAR, 
	reply_to_message_id INTEGER, 
	thread_id VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(conversation_id) REFERENCES live_chat_conversations (id), 
	FOREIGN KEY(agent_id) REFERENCES agents (id), 
	FOREIGN KEY(reply_to_message_id) REFERENCES live_chat_messages (id)
);

-- Indexes for live_chat_messages
CREATE INDEX ix_live_chat_messages_id ON live_chat_messages (id);

-- Table: live_chat_settings
DROP TABLE IF EXISTS live_chat_settings CASCADE;
CREATE TABLE live_chat_settings (
	id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	is_enabled BOOLEAN, 
	welcome_message TEXT, 
	offline_message TEXT, 
	pre_chat_form_enabled BOOLEAN, 
	post_chat_survey_enabled BOOLEAN, 
	max_queue_size INTEGER, 
	max_wait_time_minutes INTEGER, 
	queue_timeout_message TEXT, 
	auto_assignment_enabled BOOLEAN, 
	assignment_method VARCHAR, 
	max_chats_per_agent INTEGER, 
	business_hours_enabled BOOLEAN, 
	business_hours TEXT, 
	timezone VARCHAR, 
	email_notifications_enabled BOOLEAN, 
	escalation_email VARCHAR, 
	notification_triggers TEXT, 
	widget_color VARCHAR, 
	widget_position VARCHAR, 
	company_logo_url VARCHAR, 
	file_upload_enabled BOOLEAN, 
	file_size_limit_mb INTEGER, 
	allowed_file_types TEXT, 
	customer_info_retention_days INTEGER, 
	require_email_verification BOOLEAN, 
	created_at TIMESTAMP, 
	updated_at TIMESTAMP, 
	PRIMARY KEY (id), 
	UNIQUE (tenant_id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

-- Indexes for live_chat_settings
CREATE INDEX ix_live_chat_settings_id ON live_chat_settings (id);

-- Table: password_resets
DROP TABLE IF EXISTS password_resets CASCADE;
CREATE TABLE password_resets (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	token VARCHAR NOT NULL, 
	expires_at TIMESTAMP NOT NULL, 
	is_used BOOLEAN, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

-- Indexes for password_resets
CREATE INDEX ix_password_resets_id ON password_resets (id);
CREATE UNIQUE INDEX ix_password_resets_token ON password_resets (token);

-- Table: pending_feedback
DROP TABLE IF EXISTS pending_feedback CASCADE;
CREATE TABLE pending_feedback (
	id INTEGER NOT NULL, 
	feedback_id VARCHAR, 
	tenant_id INTEGER, 
	session_id VARCHAR, 
	user_email VARCHAR, 
	user_question TEXT, 
	bot_response TEXT, 
	conversation_context TEXT, 
	tenant_email_sent BOOLEAN, 
	tenant_email_id VARCHAR, 
	tenant_response TEXT, 
	user_notified BOOLEAN, 
	user_email_id VARCHAR, 
	form_accessed BOOLEAN, 
	form_accessed_at TIMESTAMP, 
	form_expired BOOLEAN, 
	add_to_faq BOOLEAN, 
	faq_question TEXT, 
	faq_answer TEXT, 
	faq_created BOOLEAN, 
	status VARCHAR, 
	created_at TIMESTAMP, 
	tenant_notified_at TIMESTAMP, 
	resolved_at TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(session_id) REFERENCES chat_sessions (session_id)
);

-- Indexes for pending_feedback
CREATE UNIQUE INDEX ix_pending_feedback_feedback_id ON pending_feedback (feedback_id);
CREATE INDEX ix_pending_feedback_id ON pending_feedback (id);

-- Table: pricing_plans
DROP TABLE IF EXISTS pricing_plans CASCADE;
CREATE TABLE pricing_plans (
	id INTEGER NOT NULL, 
	name VARCHAR, 
	plan_type VARCHAR, 
	price_monthly NUMERIC(10, 2), 
	price_yearly NUMERIC(10, 2), 
	max_integrations INTEGER, 
	max_messages_monthly INTEGER, 
	custom_prompt_allowed BOOLEAN, 
	website_api_allowed BOOLEAN, 
	slack_allowed BOOLEAN, 
	discord_allowed BOOLEAN, 
	whatsapp_allowed BOOLEAN, 
	features TEXT, 
	is_active BOOLEAN, 
	is_addon BOOLEAN, 
	is_popular BOOLEAN, 
	display_order INTEGER, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id)
);

-- Indexes for pricing_plans
CREATE INDEX ix_pricing_plans_id ON pricing_plans (id);
CREATE UNIQUE INDEX ix_pricing_plans_name ON pricing_plans (name);
CREATE INDEX ix_pricing_plans_plan_type ON pricing_plans (plan_type);

-- Table: scraped_emails
DROP TABLE IF EXISTS scraped_emails CASCADE;
CREATE TABLE scraped_emails (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email VARCHAR(254) NOT NULL,
            email_hash VARCHAR(32) UNIQUE NOT NULL,
            source VARCHAR(50) NOT NULL,
            capture_method VARCHAR(50) NOT NULL,
            session_id VARCHAR(255) REFERENCES chat_sessions(session_id) ON DELETE SET NULL,
            user_agent TEXT,
            referrer_url TEXT,
            ip_address VARCHAR(45),
            consent_given BOOLEAN DEFAULT 0 NOT NULL,
            verified BOOLEAN DEFAULT 0 NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
        );

-- Indexes for scraped_emails
CREATE INDEX idx_scraped_emails_created_at ON scraped_emails(created_at);
CREATE INDEX idx_scraped_emails_email ON scraped_emails(email);
CREATE INDEX idx_scraped_emails_session_id ON scraped_emails(session_id);
CREATE INDEX idx_scraped_emails_source ON scraped_emails(source);
CREATE INDEX idx_scraped_emails_tenant_id ON scraped_emails(tenant_id);
CREATE INDEX idx_scraped_emails_verified ON scraped_emails(verified);

-- Table: security_incidents
DROP TABLE IF EXISTS security_incidents CASCADE;
CREATE TABLE security_incidents (
	id INTEGER NOT NULL, 
	tenant_id INTEGER, 
	session_id VARCHAR, 
	user_identifier VARCHAR, 
	platform VARCHAR, 
	risk_type VARCHAR(50), 
	user_message TEXT, 
	security_response TEXT, 
	matched_patterns TEXT, 
	severity_score INTEGER, 
	detected_at TIMESTAMP, 
	reviewed BOOLEAN, 
	reviewer_notes TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

-- Indexes for security_incidents
CREATE INDEX ix_security_incidents_id ON security_incidents (id);
CREATE INDEX ix_security_incidents_user_identifier ON security_incidents (user_identifier);

-- Table: slack_channel_context
DROP TABLE IF EXISTS slack_channel_context CASCADE;
CREATE TABLE slack_channel_context (
	id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	channel_id VARCHAR(50) NOT NULL, 
	channel_name VARCHAR(100), 
	channel_type VARCHAR(20), 
	bot_enabled BOOLEAN, 
	thread_mode VARCHAR(20), 
	channel_topic TEXT, 
	common_questions TEXT, 
	channel_personality TEXT, 
	total_messages INTEGER, 
	active_threads INTEGER, 
	last_activity TIMESTAMP, 
	created_at TIMESTAMP, 
	PRIMARY KEY (id)
);

-- Indexes for slack_channel_context
CREATE INDEX idx_slack_channel_tenant ON slack_channel_context (tenant_id, channel_id);
CREATE INDEX ix_slack_channel_context_channel_id ON slack_channel_context (channel_id);
CREATE INDEX ix_slack_channel_context_id ON slack_channel_context (id);
CREATE INDEX ix_slack_channel_context_tenant_id ON slack_channel_context (tenant_id);

-- Table: slack_thread_memory
DROP TABLE IF EXISTS slack_thread_memory CASCADE;
CREATE TABLE slack_thread_memory (
	id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	channel_id VARCHAR(50) NOT NULL, 
	thread_ts VARCHAR(50), 
	user_id VARCHAR(50) NOT NULL, 
	conversation_context TEXT, 
	user_preferences TEXT, 
	topic_summary TEXT, 
	message_count INTEGER, 
	last_activity TIMESTAMP, 
	is_active BOOLEAN, 
	created_at TIMESTAMP, 
	PRIMARY KEY (id)
);

-- Indexes for slack_thread_memory
CREATE INDEX idx_slack_thread_tenant_channel ON slack_thread_memory (tenant_id, channel_id);
CREATE INDEX idx_slack_thread_ts ON slack_thread_memory (thread_ts);
CREATE INDEX idx_slack_thread_user_activity ON slack_thread_memory (user_id, last_activity);
CREATE INDEX ix_slack_thread_memory_channel_id ON slack_thread_memory (channel_id);
CREATE INDEX ix_slack_thread_memory_id ON slack_thread_memory (id);
CREATE INDEX ix_slack_thread_memory_tenant_id ON slack_thread_memory (tenant_id);
CREATE INDEX ix_slack_thread_memory_thread_ts ON slack_thread_memory (thread_ts);
CREATE INDEX ix_slack_thread_memory_user_id ON slack_thread_memory (user_id);

-- Table: smart_routing_log
DROP TABLE IF EXISTS smart_routing_log CASCADE;
CREATE TABLE smart_routing_log (
	id INTEGER NOT NULL, 
	conversation_id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	assigned_agent_id INTEGER, 
	routing_method VARCHAR(50) NOT NULL, 
	confidence_score FLOAT, 
	detected_tags JSON, 
	customer_context JSON, 
	available_agents JSON, 
	scoring_breakdown JSON, 
	fallback_reason VARCHAR(200), 
	alternative_agents JSON, 
	customer_satisfaction INTEGER, 
	resolution_time_minutes INTEGER, 
	was_transferred BOOLEAN, 
	transfer_reason VARCHAR(200), 
	routing_accuracy FLOAT, 
	success_factors JSON, 
	improvement_suggestions JSON, 
	routed_at TIMESTAMP, 
	conversation_ended_at TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(conversation_id) REFERENCES live_chat_conversations (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(assigned_agent_id) REFERENCES agents (id)
);

-- Indexes for smart_routing_log
CREATE INDEX ix_smart_routing_log_id ON smart_routing_log (id);

-- Table: telegram_chats
DROP TABLE IF EXISTS telegram_chats CASCADE;
CREATE TABLE telegram_chats (
	id INTEGER NOT NULL, 
	tenant_id INTEGER, 
	telegram_integration_id INTEGER, 
	chat_id VARCHAR NOT NULL, 
	chat_type VARCHAR NOT NULL, 
	user_id VARCHAR, 
	username VARCHAR, 
	first_name VARCHAR, 
	last_name VARCHAR, 
	is_active BOOLEAN, 
	language_code VARCHAR, 
	first_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	total_messages INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(telegram_integration_id) REFERENCES telegram_integrations (id)
);

-- Indexes for telegram_chats
CREATE INDEX ix_telegram_chats_chat_id ON telegram_chats (chat_id);
CREATE INDEX ix_telegram_chats_id ON telegram_chats (id);
CREATE INDEX ix_telegram_chats_tenant_id ON telegram_chats (tenant_id);
CREATE INDEX ix_telegram_chats_user_id ON telegram_chats (user_id);

-- Table: telegram_integrations
DROP TABLE IF EXISTS telegram_integrations CASCADE;
CREATE TABLE telegram_integrations (
	id INTEGER NOT NULL, 
	tenant_id INTEGER, 
	bot_token VARCHAR NOT NULL, 
	bot_username VARCHAR, 
	bot_name VARCHAR, 
	webhook_url VARCHAR, 
	webhook_secret VARCHAR, 
	is_active BOOLEAN, 
	is_webhook_set BOOLEAN, 
	enable_groups BOOLEAN, 
	enable_privacy_mode BOOLEAN, 
	enable_inline_mode BOOLEAN, 
	welcome_message TEXT, 
	help_message TEXT, 
	enable_typing_indicator BOOLEAN, 
	max_messages_per_minute INTEGER, 
	last_webhook_received TIMESTAMP, 
	last_message_sent TIMESTAMP, 
	total_messages_received INTEGER, 
	total_messages_sent INTEGER, 
	last_error TEXT, 
	error_count INTEGER, 
	last_error_at TIMESTAMP, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP, 
	activated_at TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

-- Indexes for telegram_integrations
CREATE INDEX ix_telegram_integrations_id ON telegram_integrations (id);
CREATE UNIQUE INDEX ix_telegram_integrations_tenant_id ON telegram_integrations (tenant_id);

-- Table: tenant_credentials
DROP TABLE IF EXISTS tenant_credentials CASCADE;
CREATE TABLE tenant_credentials (
	tenant_id INTEGER NOT NULL, 
	hashed_password VARCHAR, 
	password_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (tenant_id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

-- Table: tenant_password_resets
DROP TABLE IF EXISTS tenant_password_resets CASCADE;
CREATE TABLE tenant_password_resets (
	id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	token VARCHAR NOT NULL, 
	created_at TIMESTAMP, 
	expires_at TIMESTAMP NOT NULL, 
	is_used BOOLEAN, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

-- Indexes for tenant_password_resets
CREATE INDEX ix_tenant_password_resets_id ON tenant_password_resets (id);
CREATE UNIQUE INDEX ix_tenant_password_resets_token ON tenant_password_resets (token);

-- Table: tenant_subscriptions
DROP TABLE IF EXISTS tenant_subscriptions CASCADE;
CREATE TABLE tenant_subscriptions (
	id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	plan_id INTEGER NOT NULL, 
	is_active BOOLEAN, 
	billing_cycle VARCHAR, 
	current_period_start TIMESTAMP NOT NULL, 
	current_period_end TIMESTAMP NOT NULL, 
	messages_used_current_period INTEGER, 
	integrations_count INTEGER, 
	active_addons TEXT, 
	stripe_subscription_id VARCHAR, 
	stripe_customer_id VARCHAR, 
	status VARCHAR, 
	flutterwave_tx_ref VARCHAR, 
	flutterwave_flw_ref VARCHAR, 
	flutterwave_customer_id VARCHAR, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
	FOREIGN KEY(plan_id) REFERENCES pricing_plans (id)
);

-- Indexes for tenant_subscriptions
CREATE INDEX ix_tenant_subscriptions_id ON tenant_subscriptions (id);

-- Table: tenants
DROP TABLE IF EXISTS tenants CASCADE;
CREATE TABLE tenants (
	id INTEGER NOT NULL, 
	name VARCHAR, 
	business_name VARCHAR NOT NULL, 
	description TEXT, 
	api_key VARCHAR, 
	is_active BOOLEAN, 
	email VARCHAR NOT NULL, 
	supabase_user_id VARCHAR, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	feedback_email VARCHAR, 
	from_email VARCHAR, 
	enable_feedback_system BOOLEAN, 
	feedback_notification_enabled BOOLEAN, 
	is_super_tenant BOOLEAN, 
	can_impersonate BOOLEAN, 
	impersonating_tenant_id INTEGER, 
	discord_bot_token VARCHAR, 
	discord_application_id VARCHAR, 
	discord_enabled BOOLEAN, 
	discord_status_message VARCHAR, 
	slack_bot_token VARCHAR, 
	slack_signing_secret VARCHAR, 
	slack_app_id VARCHAR, 
	slack_client_id VARCHAR, 
	slack_client_secret VARCHAR, 
	slack_enabled BOOLEAN, 
	slack_team_id VARCHAR, 
	slack_bot_user_id VARCHAR, 
	system_prompt TEXT, 
	system_prompt_validated BOOLEAN, 
	system_prompt_updated_at TIMESTAMP, 
	security_level VARCHAR(20), 
	allow_custom_prompts BOOLEAN, 
	security_notifications_enabled BOOLEAN, 
	primary_color VARCHAR(7), 
	secondary_color VARCHAR(7), 
	text_color VARCHAR(7), 
	background_color VARCHAR(7), 
	user_bubble_color VARCHAR(7), 
	bot_bubble_color VARCHAR(7), 
	border_color VARCHAR(7), 
	logo_image_url VARCHAR, 
	logo_text VARCHAR(10), 
	border_radius VARCHAR(10), 
	widget_position VARCHAR(20), 
	font_family VARCHAR(100), 
	custom_css TEXT, 
	branding_updated_at TIMESTAMP, 
	branding_version INTEGER, 
	telegram_bot_token VARCHAR, 
	telegram_enabled BOOLEAN, 
	telegram_username VARCHAR, 
	telegram_webhook_url VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(impersonating_tenant_id) REFERENCES tenants (id)
);

-- Indexes for tenants
CREATE UNIQUE INDEX ix_tenants_api_key ON tenants (api_key);
CREATE INDEX ix_tenants_business_name ON tenants (business_name);
CREATE UNIQUE INDEX ix_tenants_email ON tenants (email);
CREATE INDEX ix_tenants_id ON tenants (id);
CREATE UNIQUE INDEX ix_tenants_name ON tenants (name);
CREATE INDEX ix_tenants_supabase_user_id ON tenants (supabase_user_id);

-- Table: usage_logs
DROP TABLE IF EXISTS usage_logs CASCADE;
CREATE TABLE usage_logs (
	id INTEGER NOT NULL, 
	subscription_id INTEGER NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	usage_type VARCHAR NOT NULL, 
	count INTEGER, 
	integration_type VARCHAR, 
	extra_data TEXT, 
	session_id VARCHAR, 
	user_identifier VARCHAR, 
	platform VARCHAR, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(subscription_id) REFERENCES tenant_subscriptions (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

-- Indexes for usage_logs
CREATE INDEX ix_usage_logs_id ON usage_logs (id);

-- Table: users
DROP TABLE IF EXISTS users CASCADE;
CREATE TABLE users (
	id INTEGER NOT NULL, 
	email VARCHAR, 
	username VARCHAR, 
	hashed_password VARCHAR, 
	is_active BOOLEAN, 
	is_admin BOOLEAN, 
	tenant_id INTEGER, 
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tenant_id) REFERENCES tenants (id)
);

-- Indexes for users
CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE INDEX ix_users_id ON users (id);
CREATE UNIQUE INDEX ix_users_username ON users (username);
