-- Schema extracted from Render PostgreSQL database
-- Modified to be compatible with Supabase (using IF NOT EXISTS)

--
-- PostgreSQL database dump
--

-- Dumped from database version 16.9 (Debian 16.9-1.pgdg120+1)
-- Dumped by pg_dump version 16.9 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

-- *not* creating schema, since initdb creates it


--
-- Name: agentstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.agentstatus AS ENUM (
    'ONLINE',
    'BUSY',
    'AWAY',
    'OFFLINE'
);


--
-- Name: chatstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.chatstatus AS ENUM (
    'WAITING',
    'ACTIVE',
    'RESOLVED',
    'ABANDONED',
    'TRANSFERRED',
    'ESCALATED'
);


--
-- Name: conversationstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.conversationstatus AS ENUM (
    'QUEUED',
    'ACTIVE',
    'RESOLVED',
    'ABANDONED'
);


--
-- Name: documenttype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.documenttype AS ENUM (
    'PDF',
    'DOC',
    'DOCX',
    'TXT',
    'CSV',
    'XLSX',
    'website',
    'WEBSITE'
);


--
-- Name: messagetype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.messagetype AS ENUM (
    'TEXT',
    'IMAGE',
    'FILE',
    'SYSTEM',
    'HANDOFF'
);


--
-- Name: processingstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.processingstatus AS ENUM (
    'PENDING',
    'PROCESSING',
    'COMPLETED',
    'FAILED'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: admins; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.admins (
    id integer NOT NULL,
    username character varying NOT NULL,
    email character varying NOT NULL,
    name character varying NOT NULL,
    hashed_password character varying NOT NULL,
    is_active boolean,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: admins_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.admins_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: admins_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.admins_id_seq OWNED BY public.admins.id;


--
-- Name: agent_permission_overrides; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.agent_permission_overrides (
    id integer NOT NULL,
    agent_id integer NOT NULL,
    permission character varying NOT NULL,
    granted boolean,
    granted_by integer,
    granted_at timestamp without time zone,
    reason text
);


--
-- Name: agent_permission_overrides_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agent_permission_overrides_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agent_permission_overrides_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agent_permission_overrides_id_seq OWNED BY public.agent_permission_overrides.id;


--
-- Name: agent_role_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.agent_role_history (
    id integer NOT NULL,
    agent_id integer NOT NULL,
    old_role character varying,
    new_role character varying NOT NULL,
    changed_by integer,
    changed_at timestamp without time zone,
    reason text
);


--
-- Name: agent_role_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agent_role_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agent_role_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agent_role_history_id_seq OWNED BY public.agent_role_history.id;


--
-- Name: agent_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.agent_sessions (
    id integer NOT NULL,
    agent_id integer NOT NULL,
    tenant_id integer NOT NULL,
    session_id character varying NOT NULL,
    status character varying DEFAULT 'offline'::character varying,
    login_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    logout_at timestamp without time zone,
    last_activity timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    active_conversations integer DEFAULT 0,
    max_concurrent_chats integer DEFAULT 3,
    is_accepting_chats boolean DEFAULT true,
    messages_sent integer DEFAULT 0,
    conversations_handled integer DEFAULT 0,
    average_response_time double precision,
    total_online_time integer DEFAULT 0,
    ip_address character varying,
    user_agent character varying,
    websocket_id character varying,
    device_type character varying,
    browser character varying,
    status_message character varying,
    away_message character varying
);


--
-- Name: agent_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agent_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agent_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agent_sessions_id_seq OWNED BY public.agent_sessions.id;


--
-- Name: agent_tag_performance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.agent_tag_performance (
    id integer NOT NULL,
    agent_id integer NOT NULL,
    tag_id integer NOT NULL,
    total_conversations integer DEFAULT 0,
    successful_resolutions integer DEFAULT 0,
    average_resolution_time real DEFAULT 0.0,
    customer_satisfaction_avg real DEFAULT 0.0,
    conversations_last_30_days integer DEFAULT 0,
    satisfaction_last_30_days real DEFAULT 0.0,
    proficiency_level integer DEFAULT 3,
    improvement_trend real DEFAULT 0.0,
    certified boolean DEFAULT false,
    certification_date timestamp without time zone,
    last_training_date timestamp without time zone,
    is_available_for_tag boolean DEFAULT true,
    max_concurrent_for_tag integer DEFAULT 2,
    current_active_conversations integer DEFAULT 0,
    last_updated timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    last_conversation_date timestamp without time zone
);


--
-- Name: agent_tag_performance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agent_tag_performance_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agent_tag_performance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agent_tag_performance_id_seq OWNED BY public.agent_tag_performance.id;


--
-- Name: agent_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.agent_tags (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    name character varying(50) NOT NULL,
    display_name character varying(100) NOT NULL,
    category character varying(50) NOT NULL,
    description text,
    color character varying(7) DEFAULT '#6366f1'::character varying,
    icon character varying(50),
    priority_weight real DEFAULT 1.0,
    is_active boolean DEFAULT true,
    keywords jsonb,
    routing_rules jsonb,
    total_conversations integer DEFAULT 0,
    success_rate real DEFAULT 0.0,
    average_satisfaction real DEFAULT 0.0,
    created_by integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: agent_tags_association; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.agent_tags_association (
    agent_id integer NOT NULL,
    tag_id integer NOT NULL,
    proficiency_level integer DEFAULT 3,
    assigned_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    assigned_by integer
);


--
-- Name: agent_tags_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agent_tags_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agent_tags_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agent_tags_id_seq OWNED BY public.agent_tags.id;


--
-- Name: agents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.agents (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    email character varying NOT NULL,
    full_name character varying NOT NULL,
    display_name character varying,
    avatar_url character varying,
    password_hash character varying,
    invite_token character varying,
    invited_by integer NOT NULL,
    invited_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    password_set_at timestamp without time zone,
    status character varying DEFAULT 'invited'::character varying,
    is_active boolean DEFAULT true,
    last_login timestamp without time zone,
    last_seen timestamp without time zone,
    is_online boolean DEFAULT false,
    total_conversations integer DEFAULT 0,
    total_messages_sent integer DEFAULT 0,
    average_response_time double precision,
    customer_satisfaction_avg double precision,
    conversations_today integer DEFAULT 0,
    notification_settings text,
    timezone character varying DEFAULT 'UTC'::character varying,
    max_concurrent_chats integer DEFAULT 3,
    auto_assign boolean DEFAULT true,
    work_hours_start character varying,
    work_hours_end character varying,
    work_days character varying,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    primary_specialization character varying(50),
    secondary_specializations jsonb,
    skill_level integer DEFAULT 3,
    accepts_overflow boolean DEFAULT true,
    role character varying DEFAULT 'member'::character varying,
    promoted_at timestamp without time zone,
    promoted_by integer,
    can_assign_conversations boolean DEFAULT false,
    can_manage_team boolean DEFAULT false,
    can_access_analytics boolean DEFAULT false
);


--
-- Name: agents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agents_id_seq OWNED BY public.agents.id;


--
-- Name: billing_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.billing_history (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    subscription_id integer NOT NULL,
    amount numeric(10,2) NOT NULL,
    currency character varying,
    billing_period_start timestamp without time zone NOT NULL,
    billing_period_end timestamp without time zone NOT NULL,
    plan_name character varying,
    conversations_included integer,
    conversations_used integer,
    addons_included text,
    stripe_invoice_id character varying,
    stripe_charge_id character varying,
    payment_status character varying,
    payment_date timestamp without time zone,
    payment_method character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: billing_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.billing_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: billing_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.billing_history_id_seq OWNED BY public.billing_history.id;


--
-- Name: booking_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.booking_requests (
    id integer NOT NULL,
    tenant_id integer,
    session_id character varying,
    user_identifier character varying,
    user_email character varying,
    user_name character varying,
    calendly_event_uri character varying,
    calendly_event_uuid character varying,
    booking_url character varying,
    status character varying,
    booking_message text,
    created_at timestamp without time zone,
    booked_at timestamp without time zone
);


--
-- Name: booking_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.booking_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: booking_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.booking_requests_id_seq OWNED BY public.booking_requests.id;


--
-- Name: chat_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.chat_messages (
    id integer NOT NULL,
    session_id integer,
    content text,
    translated_content text,
    source_language character varying(10),
    target_language character varying(10),
    is_from_user boolean,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: chat_messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chat_messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chat_messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chat_messages_id_seq OWNED BY public.chat_messages.id;


--
-- Name: chat_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.chat_queue (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    conversation_id integer NOT NULL,
    "position" integer NOT NULL,
    priority integer DEFAULT 1,
    estimated_wait_time integer,
    preferred_agent_id integer,
    assignment_criteria text,
    skills_required text,
    language_preference character varying,
    entry_reason character varying,
    queue_source character varying,
    queued_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    assigned_at timestamp without time zone,
    removed_at timestamp without time zone,
    status character varying DEFAULT 'waiting'::character varying,
    abandon_reason character varying,
    customer_message_preview text,
    urgency_indicators text
);


--
-- Name: chat_queue_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chat_queue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chat_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chat_queue_id_seq OWNED BY public.chat_queue.id;


--
-- Name: chat_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.chat_sessions (
    id integer NOT NULL,
    session_id character varying,
    tenant_id integer,
    user_identifier character varying,
    language_code character varying(10),
    is_active boolean,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    user_email character varying,
    discord_channel_id character varying,
    discord_user_id character varying,
    discord_guild_id character varying,
    platform character varying,
    email_captured_at timestamp without time zone,
    email_expires_at timestamp without time zone
);


--
-- Name: chat_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chat_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chat_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chat_sessions_id_seq OWNED BY public.chat_sessions.id;


--
-- Name: conversation_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.conversation_sessions (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    user_identifier character varying NOT NULL,
    platform character varying NOT NULL,
    started_at timestamp without time zone NOT NULL,
    last_activity timestamp without time zone NOT NULL,
    is_active boolean,
    message_count integer,
    duration_minutes integer,
    counted_for_billing boolean,
    billing_period_start timestamp without time zone,
    extra_data text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: conversation_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.conversation_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: conversation_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.conversation_sessions_id_seq OWNED BY public.conversation_sessions.id;


--
-- Name: conversation_tagging; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.conversation_tagging (
    id integer NOT NULL,
    conversation_id integer NOT NULL,
    tag_id integer NOT NULL,
    confidence_score real DEFAULT 0.0,
    detection_method character varying(50) NOT NULL,
    detected_keywords jsonb,
    message_text text,
    message_id integer,
    influenced_routing boolean DEFAULT false,
    routing_weight real DEFAULT 0.0,
    human_verified boolean DEFAULT false,
    verified_by integer,
    verified_at timestamp without time zone,
    detected_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: conversation_tagging_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.conversation_tagging_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: conversation_tagging_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.conversation_tagging_id_seq OWNED BY public.conversation_tagging.id;


--
-- Name: conversation_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.conversation_tags (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    name character varying NOT NULL,
    color character varying,
    description character varying,
    usage_count integer,
    created_by_agent_id integer,
    created_at timestamp without time zone
);


--
-- Name: conversation_tags_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.conversation_tags_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: conversation_tags_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.conversation_tags_id_seq OWNED BY public.conversation_tags.id;


--
-- Name: conversation_transfers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.conversation_transfers (
    id integer NOT NULL,
    conversation_id integer NOT NULL,
    tenant_id integer NOT NULL,
    from_agent_id integer NOT NULL,
    to_agent_id integer,
    transfer_reason character varying,
    transfer_notes text,
    status character varying,
    initiated_at timestamp without time zone,
    completed_at timestamp without time zone,
    conversation_summary text,
    customer_context text
);


--
-- Name: conversation_transfers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.conversation_transfers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: conversation_transfers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.conversation_transfers_id_seq OWNED BY public.conversation_transfers.id;


--
-- Name: conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.conversations (
    id integer NOT NULL,
    session_id character varying,
    tenant_id integer NOT NULL,
    customer_id character varying,
    customer_name character varying,
    customer_email character varying,
    platform character varying,
    agent_id integer,
    status public.conversationstatus,
    department character varying,
    subject character varying,
    bot_session_id character varying,
    handoff_reason text,
    bot_context text,
    queue_time_seconds integer,
    first_response_time_seconds integer,
    resolution_time_seconds integer,
    satisfaction_rating integer,
    created_at timestamp with time zone DEFAULT now(),
    assigned_at timestamp with time zone,
    resolved_at timestamp with time zone
);


--
-- Name: conversations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.conversations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: conversations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.conversations_id_seq OWNED BY public.conversations.id;


--
-- Name: customer_devices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.customer_devices (
    id integer NOT NULL,
    customer_profile_id integer NOT NULL,
    device_fingerprint character varying(255) NOT NULL,
    device_type character varying(50),
    browser_name character varying(100),
    browser_version character varying(50),
    operating_system character varying(100),
    screen_resolution character varying(50),
    supports_websockets boolean DEFAULT true,
    supports_file_upload boolean DEFAULT true,
    supports_notifications boolean DEFAULT false,
    first_seen timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    last_seen timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    total_sessions integer DEFAULT 1
);


--
-- Name: customer_devices_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.customer_devices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: customer_devices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.customer_devices_id_seq OWNED BY public.customer_devices.id;


--
-- Name: customer_preferences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.customer_preferences (
    id integer NOT NULL,
    customer_profile_id integer NOT NULL,
    preferred_language character varying(10) DEFAULT 'en'::character varying,
    preferred_agent_gender character varying(20),
    preferred_communication_style character varying(50),
    email_notifications boolean DEFAULT false,
    sms_notifications boolean DEFAULT false,
    browser_notifications boolean DEFAULT false,
    requires_accessibility_features boolean DEFAULT false,
    accessibility_preferences jsonb,
    data_retention_preference character varying(50) DEFAULT 'standard'::character varying,
    third_party_sharing_consent boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: customer_preferences_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.customer_preferences_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: customer_preferences_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.customer_preferences_id_seq OWNED BY public.customer_preferences.id;


--
-- Name: customer_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.customer_profiles (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    customer_identifier character varying(255) NOT NULL,
    first_seen timestamp without time zone,
    last_seen timestamp without time zone,
    total_conversations integer DEFAULT 0,
    total_sessions integer DEFAULT 0,
    preferred_language character varying(50),
    time_zone character varying(50),
    preferred_contact_method character varying(50),
    customer_satisfaction_avg real,
    average_session_duration integer,
    total_messages_sent integer DEFAULT 0,
    data_collection_consent boolean DEFAULT false,
    marketing_consent boolean DEFAULT false,
    last_consent_update timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: customer_profiles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.customer_profiles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: customer_profiles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.customer_profiles_id_seq OWNED BY public.customer_profiles.id;


--
-- Name: customer_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.customer_sessions (
    id integer NOT NULL,
    customer_profile_id integer NOT NULL,
    session_id character varying(255) NOT NULL,
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    ended_at timestamp without time zone,
    duration_seconds integer,
    ip_address character varying(45),
    user_agent text,
    device_fingerprint character varying(255),
    country character varying(100),
    region character varying(100),
    city character varying(100),
    page_views integer DEFAULT 0,
    conversations_started integer DEFAULT 0
);


--
-- Name: customer_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.customer_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: customer_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.customer_sessions_id_seq OWNED BY public.customer_sessions.id;


--
-- Name: faqs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.faqs (
    id integer NOT NULL,
    tenant_id integer,
    question text,
    answer text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


--
-- Name: faqs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.faqs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: faqs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.faqs_id_seq OWNED BY public.faqs.id;


--
-- Name: instagram_conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.instagram_conversations (
    id integer NOT NULL,
    integration_id integer,
    tenant_id integer,
    instagram_user_id character varying NOT NULL,
    instagram_username character varying,
    user_profile_name character varying,
    user_profile_picture character varying,
    conversation_id character varying,
    thread_id character varying,
    is_active boolean,
    conversation_status character varying,
    conversation_source character varying,
    initial_message_type character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    last_message_at timestamp without time zone,
    last_user_message_at timestamp without time zone,
    last_bot_message_at timestamp without time zone,
    total_messages integer,
    user_messages integer,
    bot_messages integer
);


--
-- Name: instagram_conversations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.instagram_conversations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: instagram_conversations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.instagram_conversations_id_seq OWNED BY public.instagram_conversations.id;


--
-- Name: instagram_integrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.instagram_integrations (
    id integer NOT NULL,
    tenant_id integer,
    meta_app_id character varying NOT NULL,
    meta_app_secret character varying NOT NULL,
    instagram_business_account_id character varying NOT NULL,
    instagram_username character varying NOT NULL,
    facebook_page_id character varying NOT NULL,
    facebook_page_name character varying,
    page_access_token text NOT NULL,
    token_expires_at timestamp without time zone,
    webhook_verify_token character varying NOT NULL,
    webhook_subscribed boolean,
    webhook_subscription_fields json,
    bot_enabled boolean,
    bot_status character varying,
    auto_reply_enabled boolean,
    business_verification_required boolean,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    last_message_at timestamp without time zone,
    last_error text,
    error_count integer
);


--
-- Name: instagram_integrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.instagram_integrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: instagram_integrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.instagram_integrations_id_seq OWNED BY public.instagram_integrations.id;


--
-- Name: instagram_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.instagram_messages (
    id integer NOT NULL,
    conversation_id integer,
    tenant_id integer,
    instagram_message_id character varying,
    message_uuid character varying,
    message_type character varying,
    content text,
    media_url character varying,
    media_type character varying,
    media_size integer,
    is_from_user boolean,
    message_status character varying,
    reply_to_story boolean,
    story_id character varying,
    quick_reply_payload character varying,
    created_at timestamp with time zone DEFAULT now(),
    instagram_timestamp timestamp without time zone,
    delivered_at timestamp without time zone,
    read_at timestamp without time zone,
    send_error text,
    retry_count integer,
    raw_webhook_data json
);


--
-- Name: instagram_messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.instagram_messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: instagram_messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.instagram_messages_id_seq OWNED BY public.instagram_messages.id;


--
-- Name: instagram_webhook_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.instagram_webhook_events (
    id integer NOT NULL,
    tenant_id integer,
    integration_id integer,
    event_type character varying NOT NULL,
    event_id character varying,
    instagram_user_id character varying,
    processing_status character varying,
    processing_error text,
    processed_at timestamp without time zone,
    raw_payload json NOT NULL,
    headers json,
    received_at timestamp with time zone DEFAULT now(),
    instagram_timestamp timestamp without time zone
);


--
-- Name: instagram_webhook_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.instagram_webhook_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: instagram_webhook_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.instagram_webhook_events_id_seq OWNED BY public.instagram_webhook_events.id;


--
-- Name: knowledge_bases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.knowledge_bases (
    id integer NOT NULL,
    tenant_id integer,
    name character varying,
    description text,
    file_path character varying,
    document_type public.documenttype,
    vector_store_id character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    processing_status public.processingstatus DEFAULT 'PENDING'::public.processingstatus,
    processing_error text,
    processed_at timestamp without time zone,
    base_url character varying(500),
    crawl_depth integer DEFAULT 3,
    crawl_frequency_hours integer DEFAULT 24,
    last_crawled_at timestamp with time zone,
    pages_crawled integer DEFAULT 0,
    include_patterns jsonb,
    exclude_patterns jsonb
);


--
-- Name: knowledge_bases_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.knowledge_bases_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: knowledge_bases_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.knowledge_bases_id_seq OWNED BY public.knowledge_bases.id;


--
-- Name: live_chat_conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.live_chat_conversations (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    customer_identifier character varying NOT NULL,
    customer_email character varying,
    customer_name character varying,
    customer_phone character varying,
    customer_ip character varying,
    customer_user_agent text,
    chatbot_session_id character varying,
    handoff_reason character varying,
    handoff_trigger character varying,
    handoff_context text,
    original_question text,
    status character varying DEFAULT 'queued'::character varying,
    queue_position integer,
    priority_level integer DEFAULT 1,
    queue_entry_time timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    assigned_agent_id integer,
    assigned_at timestamp without time zone,
    assignment_method character varying,
    previous_agent_id integer,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    first_response_at timestamp without time zone,
    last_activity_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    closed_at timestamp without time zone,
    wait_time_seconds integer,
    response_time_seconds integer,
    conversation_duration_seconds integer,
    message_count integer DEFAULT 0,
    agent_message_count integer DEFAULT 0,
    customer_message_count integer DEFAULT 0,
    customer_satisfaction integer,
    customer_feedback text,
    satisfaction_submitted_at timestamp without time zone,
    closed_by character varying,
    closure_reason character varying,
    resolution_status character varying,
    agent_notes text,
    internal_notes text,
    tags text,
    category character varying,
    department character varying,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: live_chat_conversations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.live_chat_conversations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: live_chat_conversations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.live_chat_conversations_id_seq OWNED BY public.live_chat_conversations.id;


--
-- Name: live_chat_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.live_chat_messages (
    id integer NOT NULL,
    conversation_id integer NOT NULL,
    content text NOT NULL,
    message_type character varying DEFAULT 'text'::character varying,
    raw_content text,
    sender_type character varying NOT NULL,
    sender_id character varying,
    agent_id integer,
    sender_name character varying,
    sender_avatar character varying,
    sent_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    delivered_at timestamp without time zone,
    read_at timestamp without time zone,
    edited_at timestamp without time zone,
    is_internal boolean DEFAULT false,
    is_edited boolean DEFAULT false,
    is_deleted boolean DEFAULT false,
    deleted_at timestamp without time zone,
    attachment_url character varying,
    attachment_name character varying,
    attachment_type character varying,
    attachment_size integer,
    system_event_type character varying,
    system_event_data text,
    client_message_id character varying,
    reply_to_message_id integer,
    thread_id character varying
);


--
-- Name: live_chat_messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.live_chat_messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: live_chat_messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.live_chat_messages_id_seq OWNED BY public.live_chat_messages.id;


--
-- Name: live_chat_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.live_chat_settings (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    is_enabled boolean DEFAULT true,
    welcome_message text,
    offline_message text,
    pre_chat_form_enabled boolean DEFAULT false,
    post_chat_survey_enabled boolean DEFAULT true,
    max_queue_size integer DEFAULT 50,
    max_wait_time_minutes integer DEFAULT 30,
    queue_timeout_message text,
    auto_assignment_enabled boolean DEFAULT true,
    assignment_method character varying DEFAULT 'round_robin'::character varying,
    max_chats_per_agent integer DEFAULT 3,
    business_hours_enabled boolean DEFAULT false,
    business_hours text,
    timezone character varying DEFAULT 'UTC'::character varying,
    email_notifications_enabled boolean DEFAULT true,
    escalation_email character varying,
    notification_triggers text,
    widget_color character varying DEFAULT '#6d28d9'::character varying,
    widget_position character varying DEFAULT 'bottom-right'::character varying,
    company_logo_url character varying,
    file_upload_enabled boolean DEFAULT true,
    file_size_limit_mb integer DEFAULT 10,
    allowed_file_types text,
    customer_info_retention_days integer DEFAULT 365,
    require_email_verification boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: live_chat_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.live_chat_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: live_chat_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.live_chat_settings_id_seq OWNED BY public.live_chat_settings.id;


--
-- Name: live_chats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.live_chats (
    id integer NOT NULL,
    session_id character varying,
    tenant_id integer NOT NULL,
    user_identifier character varying NOT NULL,
    user_name character varying,
    user_email character varying,
    platform character varying,
    agent_id integer,
    assigned_at timestamp with time zone,
    status public.chatstatus,
    subject character varying,
    priority character varying,
    department character varying,
    chatbot_session_id character varying,
    handoff_reason text,
    bot_context text,
    queue_time integer,
    first_response_time integer,
    resolution_time integer,
    customer_satisfaction integer,
    started_at timestamp with time zone DEFAULT now(),
    ended_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


--
-- Name: live_chats_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.live_chats_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: live_chats_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.live_chats_id_seq OWNED BY public.live_chats.id;


--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.messages (
    id integer NOT NULL,
    conversation_id integer NOT NULL,
    content text NOT NULL,
    message_type public.messagetype,
    from_agent boolean,
    sender_name character varying,
    agent_id integer,
    created_at timestamp with time zone DEFAULT now(),
    read_at timestamp with time zone
);


--
-- Name: messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.messages_id_seq OWNED BY public.messages.id;


--
-- Name: migration_backup_simple; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.migration_backup_simple (
    old_id integer,
    new_id integer,
    tenant_name character varying(255),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: password_resets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.password_resets (
    id integer NOT NULL,
    user_id integer NOT NULL,
    token character varying NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    is_used boolean,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: password_resets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.password_resets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: password_resets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.password_resets_id_seq OWNED BY public.password_resets.id;


--
-- Name: pending_feedback; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.pending_feedback (
    id integer NOT NULL,
    feedback_id character varying,
    tenant_id integer,
    session_id character varying,
    user_email character varying,
    user_question text,
    bot_response text,
    conversation_context text,
    tenant_email_sent boolean,
    tenant_email_id character varying,
    tenant_response text,
    user_notified boolean,
    user_email_id character varying,
    status character varying,
    created_at timestamp without time zone,
    tenant_notified_at timestamp without time zone,
    resolved_at timestamp without time zone,
    form_accessed boolean DEFAULT false,
    form_accessed_at timestamp without time zone,
    form_expired boolean DEFAULT false,
    add_to_faq boolean DEFAULT false,
    faq_created boolean DEFAULT false,
    faq_question text,
    faq_answer text
);


--
-- Name: pending_feedback_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pending_feedback_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pending_feedback_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pending_feedback_id_seq OWNED BY public.pending_feedback.id;


--
-- Name: pricing_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.pricing_plans (
    id integer NOT NULL,
    name character varying,
    plan_type character varying,
    price_monthly numeric(10,2),
    price_yearly numeric(10,2),
    max_integrations integer,
    max_messages_monthly integer,
    custom_prompt_allowed boolean,
    website_api_allowed boolean,
    slack_allowed boolean,
    discord_allowed boolean,
    whatsapp_allowed boolean,
    features text,
    is_active boolean,
    is_addon boolean,
    is_popular boolean,
    display_order integer,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: pricing_plans_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pricing_plans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pricing_plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pricing_plans_id_seq OWNED BY public.pricing_plans.id;


--
-- Name: scraped_emails; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.scraped_emails (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    email character varying NOT NULL,
    email_hash character varying,
    source character varying NOT NULL,
    capture_method character varying NOT NULL,
    session_id character varying,
    user_agent text,
    referrer_url text,
    ip_address character varying,
    consent_given boolean,
    verified boolean,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: scraped_emails_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.scraped_emails_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scraped_emails_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.scraped_emails_id_seq OWNED BY public.scraped_emails.id;


--
-- Name: security_incidents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.security_incidents (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    session_id character varying(255),
    user_identifier character varying(255) NOT NULL,
    platform character varying(50) DEFAULT 'web'::character varying,
    risk_type character varying(50) NOT NULL,
    user_message text NOT NULL,
    security_response text NOT NULL,
    matched_patterns text,
    severity_score integer DEFAULT 1,
    detected_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    reviewed boolean DEFAULT false,
    reviewer_notes text
);


--
-- Name: security_incidents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.security_incidents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: security_incidents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.security_incidents_id_seq OWNED BY public.security_incidents.id;


--
-- Name: slack_channel_context; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.slack_channel_context (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    channel_id character varying(50) NOT NULL,
    channel_name character varying(100),
    channel_type character varying(20),
    bot_enabled boolean,
    thread_mode character varying(20),
    channel_topic text,
    common_questions text,
    channel_personality text,
    total_messages integer,
    active_threads integer,
    last_activity timestamp without time zone,
    created_at timestamp without time zone
);


--
-- Name: slack_channel_context_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.slack_channel_context_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: slack_channel_context_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.slack_channel_context_id_seq OWNED BY public.slack_channel_context.id;


--
-- Name: slack_thread_memory; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.slack_thread_memory (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    channel_id character varying(50) NOT NULL,
    thread_ts character varying(50),
    user_id character varying(50) NOT NULL,
    conversation_context text,
    user_preferences text,
    topic_summary text,
    message_count integer,
    last_activity timestamp without time zone,
    is_active boolean,
    created_at timestamp without time zone
);


--
-- Name: slack_thread_memory_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.slack_thread_memory_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: slack_thread_memory_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.slack_thread_memory_id_seq OWNED BY public.slack_thread_memory.id;


--
-- Name: smart_routing_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.smart_routing_log (
    id integer NOT NULL,
    conversation_id integer NOT NULL,
    tenant_id integer NOT NULL,
    assigned_agent_id integer,
    routing_method character varying(50) NOT NULL,
    confidence_score real DEFAULT 0.0,
    detected_tags jsonb,
    customer_context jsonb,
    available_agents jsonb,
    scoring_breakdown jsonb,
    fallback_reason character varying(200),
    alternative_agents jsonb,
    customer_satisfaction integer,
    resolution_time_minutes integer,
    was_transferred boolean DEFAULT false,
    transfer_reason character varying(200),
    routing_accuracy real,
    success_factors jsonb,
    improvement_suggestions jsonb,
    routed_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    conversation_ended_at timestamp without time zone
);


--
-- Name: smart_routing_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.smart_routing_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: smart_routing_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.smart_routing_log_id_seq OWNED BY public.smart_routing_log.id;


--
-- Name: telegram_chats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.telegram_chats (
    id integer NOT NULL,
    tenant_id integer,
    telegram_integration_id integer,
    chat_id character varying NOT NULL,
    chat_type character varying NOT NULL,
    user_id character varying,
    username character varying,
    first_name character varying,
    last_name character varying,
    is_active boolean,
    language_code character varying,
    first_message_at timestamp without time zone DEFAULT now(),
    last_message_at timestamp without time zone DEFAULT now(),
    total_messages integer
);


--
-- Name: telegram_chats_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.telegram_chats_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: telegram_chats_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.telegram_chats_id_seq OWNED BY public.telegram_chats.id;


--
-- Name: telegram_integrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.telegram_integrations (
    id integer NOT NULL,
    tenant_id integer,
    bot_token character varying NOT NULL,
    bot_username character varying,
    bot_name character varying,
    webhook_url character varying,
    webhook_secret character varying,
    is_active boolean,
    is_webhook_set boolean,
    enable_groups boolean,
    enable_privacy_mode boolean,
    enable_inline_mode boolean,
    welcome_message text,
    help_message text,
    enable_typing_indicator boolean,
    max_messages_per_minute integer,
    last_webhook_received timestamp without time zone,
    last_message_sent timestamp without time zone,
    total_messages_received integer,
    total_messages_sent integer,
    last_error text,
    error_count integer,
    last_error_at timestamp without time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    activated_at timestamp without time zone
);


--
-- Name: telegram_integrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.telegram_integrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: telegram_integrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.telegram_integrations_id_seq OWNED BY public.telegram_integrations.id;


--
-- Name: tenant_credentials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.tenant_credentials (
    tenant_id integer NOT NULL,
    hashed_password character varying,
    password_updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: tenant_id_migration_backup; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.tenant_id_migration_backup (
    old_id integer,
    new_id integer,
    tenant_name character varying(255),
    tenant_email character varying(255),
    migration_timestamp timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    status character varying(50) DEFAULT 'pending'::character varying
);


--
-- Name: tenant_password_resets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.tenant_password_resets (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    token character varying NOT NULL,
    created_at timestamp without time zone,
    expires_at timestamp without time zone NOT NULL,
    is_used boolean
);


--
-- Name: tenant_password_resets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tenant_password_resets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tenant_password_resets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tenant_password_resets_id_seq OWNED BY public.tenant_password_resets.id;


--
-- Name: tenant_subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.tenant_subscriptions (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    plan_id integer NOT NULL,
    is_active boolean,
    billing_cycle character varying,
    current_period_start timestamp without time zone NOT NULL,
    current_period_end timestamp without time zone NOT NULL,
    messages_used_current_period integer,
    integrations_count integer,
    active_addons text,
    stripe_subscription_id character varying,
    stripe_customer_id character varying,
    status character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    flutterwave_tx_ref character varying(255),
    flutterwave_flw_ref character varying(255),
    flutterwave_customer_id character varying(255)
);


--
-- Name: tenant_subscriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tenant_subscriptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tenant_subscriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tenant_subscriptions_id_seq OWNED BY public.tenant_subscriptions.id;


--
-- Name: tenants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.tenants (
    id integer NOT NULL,
    name character varying,
    description text,
    api_key character varying,
    is_active boolean,
    email character varying NOT NULL,
    supabase_user_id character varying,
    system_prompt text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    feedback_email character varying,
    from_email character varying,
    enable_feedback_system boolean,
    feedback_notification_enabled boolean,
    contact_email character varying,
    discord_bot_token character varying,
    discord_application_id character varying,
    discord_enabled boolean,
    discord_status_message character varying,
    slack_bot_token character varying,
    slack_signing_secret character varying,
    slack_app_id character varying,
    slack_client_id character varying,
    slack_client_secret character varying,
    slack_enabled boolean,
    slack_team_id character varying,
    slack_bot_user_id character varying,
    business_name character varying NOT NULL,
    is_super_tenant boolean DEFAULT false,
    can_impersonate boolean DEFAULT false,
    impersonating_tenant_id integer,
    system_prompt_validated boolean DEFAULT false,
    system_prompt_updated_at timestamp without time zone,
    security_level character varying(20) DEFAULT 'standard'::character varying,
    allow_custom_prompts boolean DEFAULT true,
    security_notifications_enabled boolean DEFAULT true,
    primary_color character varying(7) DEFAULT '#007bff'::character varying,
    secondary_color character varying(7) DEFAULT '#f0f4ff'::character varying,
    text_color character varying(7) DEFAULT '#222222'::character varying,
    background_color character varying(7) DEFAULT '#ffffff'::character varying,
    user_bubble_color character varying(7) DEFAULT '#007bff'::character varying,
    bot_bubble_color character varying(7) DEFAULT '#f0f4ff'::character varying,
    border_color character varying(7) DEFAULT '#e0e0e0'::character varying,
    logo_image_url character varying(500),
    logo_text character varying(10),
    border_radius character varying(20) DEFAULT '12px'::character varying,
    widget_position character varying(20) DEFAULT 'bottom-right'::character varying,
    font_family character varying(100) DEFAULT 'Inter, sans-serif'::character varying,
    custom_css text,
    branding_updated_at timestamp with time zone,
    branding_version integer DEFAULT 1,
    telegram_bot_token character varying,
    telegram_enabled boolean DEFAULT false,
    telegram_username character varying,
    telegram_webhook_url character varying
);


--
-- Name: tenants_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tenants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tenants_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tenants_id_seq OWNED BY public.tenants.id;


--
-- Name: usage_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.usage_logs (
    id integer NOT NULL,
    subscription_id integer NOT NULL,
    tenant_id integer NOT NULL,
    usage_type character varying NOT NULL,
    count integer,
    integration_type character varying,
    extra_data text,
    session_id character varying,
    user_identifier character varying,
    platform character varying,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: usage_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.usage_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: usage_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.usage_logs_id_seq OWNED BY public.usage_logs.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE IF NOT EXISTS public.users (
    id integer NOT NULL,
    email character varying,
    username character varying,
    hashed_password character varying,
    is_active boolean,
    is_admin boolean,
    tenant_id integer,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: admins id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admins ALTER COLUMN id SET DEFAULT nextval('public.admins_id_seq'::regclass);


--
-- Name: agent_permission_overrides id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_permission_overrides ALTER COLUMN id SET DEFAULT nextval('public.agent_permission_overrides_id_seq'::regclass);


--
-- Name: agent_role_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_role_history ALTER COLUMN id SET DEFAULT nextval('public.agent_role_history_id_seq'::regclass);


--
-- Name: agent_sessions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_sessions ALTER COLUMN id SET DEFAULT nextval('public.agent_sessions_id_seq'::regclass);


--
-- Name: agent_tag_performance id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tag_performance ALTER COLUMN id SET DEFAULT nextval('public.agent_tag_performance_id_seq'::regclass);


--
-- Name: agent_tags id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tags ALTER COLUMN id SET DEFAULT nextval('public.agent_tags_id_seq'::regclass);


--
-- Name: agents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agents ALTER COLUMN id SET DEFAULT nextval('public.agents_id_seq'::regclass);


--
-- Name: billing_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.billing_history ALTER COLUMN id SET DEFAULT nextval('public.billing_history_id_seq'::regclass);


--
-- Name: booking_requests id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests ALTER COLUMN id SET DEFAULT nextval('public.booking_requests_id_seq'::regclass);


--
-- Name: chat_messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_messages ALTER COLUMN id SET DEFAULT nextval('public.chat_messages_id_seq'::regclass);


--
-- Name: chat_queue id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_queue ALTER COLUMN id SET DEFAULT nextval('public.chat_queue_id_seq'::regclass);


--
-- Name: chat_sessions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_sessions ALTER COLUMN id SET DEFAULT nextval('public.chat_sessions_id_seq'::regclass);


--
-- Name: conversation_sessions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_sessions ALTER COLUMN id SET DEFAULT nextval('public.conversation_sessions_id_seq'::regclass);


--
-- Name: conversation_tagging id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_tagging ALTER COLUMN id SET DEFAULT nextval('public.conversation_tagging_id_seq'::regclass);


--
-- Name: conversation_tags id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_tags ALTER COLUMN id SET DEFAULT nextval('public.conversation_tags_id_seq'::regclass);


--
-- Name: conversation_transfers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_transfers ALTER COLUMN id SET DEFAULT nextval('public.conversation_transfers_id_seq'::regclass);


--
-- Name: conversations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations ALTER COLUMN id SET DEFAULT nextval('public.conversations_id_seq'::regclass);


--
-- Name: customer_devices id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_devices ALTER COLUMN id SET DEFAULT nextval('public.customer_devices_id_seq'::regclass);


--
-- Name: customer_preferences id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_preferences ALTER COLUMN id SET DEFAULT nextval('public.customer_preferences_id_seq'::regclass);


--
-- Name: customer_profiles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_profiles ALTER COLUMN id SET DEFAULT nextval('public.customer_profiles_id_seq'::regclass);


--
-- Name: customer_sessions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_sessions ALTER COLUMN id SET DEFAULT nextval('public.customer_sessions_id_seq'::regclass);


--
-- Name: faqs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.faqs ALTER COLUMN id SET DEFAULT nextval('public.faqs_id_seq'::regclass);


--
-- Name: instagram_conversations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instagram_conversations ALTER COLUMN id SET DEFAULT nextval('public.instagram_conversations_id_seq'::regclass);


--
-- Name: instagram_integrations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instagram_integrations ALTER COLUMN id SET DEFAULT nextval('public.instagram_integrations_id_seq'::regclass);


--
-- Name: instagram_messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instagram_messages ALTER COLUMN id SET DEFAULT nextval('public.instagram_messages_id_seq'::regclass);


--
-- Name: instagram_webhook_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instagram_webhook_events ALTER COLUMN id SET DEFAULT nextval('public.instagram_webhook_events_id_seq'::regclass);


--
-- Name: knowledge_bases id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_bases ALTER COLUMN id SET DEFAULT nextval('public.knowledge_bases_id_seq'::regclass);


--
-- Name: live_chat_conversations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_chat_conversations ALTER COLUMN id SET DEFAULT nextval('public.live_chat_conversations_id_seq'::regclass);


--
-- Name: live_chat_messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_chat_messages ALTER COLUMN id SET DEFAULT nextval('public.live_chat_messages_id_seq'::regclass);


--
-- Name: live_chat_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_chat_settings ALTER COLUMN id SET DEFAULT nextval('public.live_chat_settings_id_seq'::regclass);


--
-- Name: live_chats id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_chats ALTER COLUMN id SET DEFAULT nextval('public.live_chats_id_seq'::regclass);


--
-- Name: messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages ALTER COLUMN id SET DEFAULT nextval('public.messages_id_seq'::regclass);


--
-- Name: password_resets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_resets ALTER COLUMN id SET DEFAULT nextval('public.password_resets_id_seq'::regclass);


--
-- Name: pending_feedback id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_feedback ALTER COLUMN id SET DEFAULT nextval('public.pending_feedback_id_seq'::regclass);


--
-- Name: pricing_plans id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pricing_plans ALTER COLUMN id SET DEFAULT nextval('public.pricing_plans_id_seq'::regclass);


--
-- Name: scraped_emails id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scraped_emails ALTER COLUMN id SET DEFAULT nextval('public.scraped_emails_id_seq'::regclass);


--
-- Name: security_incidents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_incidents ALTER COLUMN id SET DEFAULT nextval('public.security_incidents_id_seq'::regclass);


--
-- Name: slack_channel_context id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.slack_channel_context ALTER COLUMN id SET DEFAULT nextval('public.slack_channel_context_id_seq'::regclass);


--
-- Name: slack_thread_memory id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.slack_thread_memory ALTER COLUMN id SET DEFAULT nextval('public.slack_thread_memory_id_seq'::regclass);


--
-- Name: smart_routing_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.smart_routing_log ALTER COLUMN id SET DEFAULT nextval('public.smart_routing_log_id_seq'::regclass);


--
-- Name: telegram_chats id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telegram_chats ALTER COLUMN id SET DEFAULT nextval('public.telegram_chats_id_seq'::regclass);


--
-- Name: telegram_integrations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telegram_integrations ALTER COLUMN id SET DEFAULT nextval('public.telegram_integrations_id_seq'::regclass);


--
-- Name: tenant_password_resets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenant_password_resets ALTER COLUMN id SET DEFAULT nextval('public.tenant_password_resets_id_seq'::regclass);


--
-- Name: tenant_subscriptions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenant_subscriptions ALTER COLUMN id SET DEFAULT nextval('public.tenant_subscriptions_id_seq'::regclass);


--
-- Name: tenants id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants ALTER COLUMN id SET DEFAULT nextval('public.tenants_id_seq'::regclass);


--
-- Name: usage_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usage_logs ALTER COLUMN id SET DEFAULT nextval('public.usage_logs_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: admins admins_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admins
    ADD CONSTRAINT admins_pkey PRIMARY KEY (id);


--
-- Name: agent_permission_overrides agent_permission_overrides_agent_id_permission_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_permission_overrides
    ADD CONSTRAINT agent_permission_overrides_agent_id_permission_key UNIQUE (agent_id, permission);


--
-- Name: agent_permission_overrides agent_permission_overrides_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_permission_overrides
    ADD CONSTRAINT agent_permission_overrides_pkey PRIMARY KEY (id);


--
-- Name: agent_role_history agent_role_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_role_history
    ADD CONSTRAINT agent_role_history_pkey PRIMARY KEY (id);


--
-- Name: agent_sessions agent_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_sessions
    ADD CONSTRAINT agent_sessions_pkey PRIMARY KEY (id);


--
-- Name: agent_sessions agent_sessions_session_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_sessions
    ADD CONSTRAINT agent_sessions_session_id_key UNIQUE (session_id);


--
-- Name: agent_sessions agent_sessions_websocket_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_sessions
    ADD CONSTRAINT agent_sessions_websocket_id_key UNIQUE (websocket_id);


--
-- Name: agent_tag_performance agent_tag_performance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tag_performance
    ADD CONSTRAINT agent_tag_performance_pkey PRIMARY KEY (id);


--
-- Name: agent_tags_association agent_tags_association_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tags_association
    ADD CONSTRAINT agent_tags_association_pkey PRIMARY KEY (agent_id, tag_id);


--
-- Name: agent_tags agent_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tags
    ADD CONSTRAINT agent_tags_pkey PRIMARY KEY (id);


--
-- Name: agents agents_invite_token_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agents
    ADD CONSTRAINT agents_invite_token_key UNIQUE (invite_token);


--
-- Name: agents agents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agents
    ADD CONSTRAINT agents_pkey PRIMARY KEY (id);


--
-- Name: billing_history billing_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.billing_history
    ADD CONSTRAINT billing_history_pkey PRIMARY KEY (id);


--
-- Name: booking_requests booking_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests
    ADD CONSTRAINT booking_requests_pkey PRIMARY KEY (id);


--
-- Name: chat_messages chat_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_pkey PRIMARY KEY (id);


--
-- Name: chat_queue chat_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_queue
    ADD CONSTRAINT chat_queue_pkey PRIMARY KEY (id);


--
-- Name: chat_sessions chat_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_sessions
    ADD CONSTRAINT chat_sessions_pkey PRIMARY KEY (id);


--
-- Name: conversation_sessions conversation_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_sessions
    ADD CONSTRAINT conversation_sessions_pkey PRIMARY KEY (id);


--
-- Name: conversation_tagging conversation_tagging_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_tagging
    ADD CONSTRAINT conversation_tagging_pkey PRIMARY KEY (id);


--
-- Name: conversation_tags conversation_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_tags
    ADD CONSTRAINT conversation_tags_pkey PRIMARY KEY (id);


--
-- Name: conversation_transfers conversation_transfers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_transfers
    ADD CONSTRAINT conversation_transfers_pkey PRIMARY KEY (id);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: customer_devices customer_devices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_devices
    ADD CONSTRAINT customer_devices_pkey PRIMARY KEY (id);


--
-- Name: customer_preferences customer_preferences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_preferences
    ADD CONSTRAINT customer_preferences_pkey PRIMARY KEY (id);


--
-- Name: customer_profiles customer_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_profiles
    ADD CONSTRAINT customer_profiles_pkey PRIMARY KEY (id);


--
-- Name: customer_sessions customer_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_sessions
    ADD CONSTRAINT customer_sessions_pkey PRIMARY KEY (id);


--
-- Name: customer_sessions customer_sessions_session_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_sessions
    ADD CONSTRAINT customer_sessions_session_id_key UNIQUE (session_id);


--
-- Name: faqs faqs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.faqs
    ADD CONSTRAINT faqs_pkey PRIMARY KEY (id);


--
-- Name: instagram_conversations instagram_conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instagram_conversations
    ADD CONSTRAINT instagram_conversations_pkey PRIMARY KEY (id);


--
-- Name: instagram_integrations instagram_integrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instagram_integrations
    ADD CONSTRAINT instagram_integrations_pkey PRIMARY KEY (id);


--
-- Name: instagram_messages instagram_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instagram_messages
    ADD CONSTRAINT instagram_messages_pkey PRIMARY KEY (id);


--
-- Name: instagram_webhook_events instagram_webhook_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instagram_webhook_events
    ADD CONSTRAINT instagram_webhook_events_pkey PRIMARY KEY (id);


--
-- Name: knowledge_bases knowledge_bases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_bases
    ADD CONSTRAINT knowledge_bases_pkey PRIMARY KEY (id);


--
-- Name: knowledge_bases knowledge_bases_vector_store_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_bases
    ADD CONSTRAINT knowledge_bases_vector_store_id_key UNIQUE (vector_store_id);


--
-- Name: live_chat_conversations live_chat_conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_chat_conversations
    ADD CONSTRAINT live_chat_conversations_pkey PRIMARY KEY (id);


--
-- Name: live_chat_messages live_chat_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_chat_messages
    ADD CONSTRAINT live_chat_messages_pkey PRIMARY KEY (id);


--
-- Name: live_chat_settings live_chat_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_chat_settings
    ADD CONSTRAINT live_chat_settings_pkey PRIMARY KEY (id);


--
-- Name: live_chat_settings live_chat_settings_tenant_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_chat_settings
    ADD CONSTRAINT live_chat_settings_tenant_id_key UNIQUE (tenant_id);


--
-- Name: live_chats live_chats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_chats
    ADD CONSTRAINT live_chats_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: password_resets password_resets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_resets
    ADD CONSTRAINT password_resets_pkey PRIMARY KEY (id);


--
-- Name: pending_feedback pending_feedback_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_feedback
    ADD CONSTRAINT pending_feedback_pkey PRIMARY KEY (id);


--
-- Name: pricing_plans pricing_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pricing_plans
    ADD CONSTRAINT pricing_plans_pkey PRIMARY KEY (id);


--
-- Name: scraped_emails scraped_emails_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scraped_emails
    ADD CONSTRAINT scraped_emails_pkey PRIMARY KEY (id);


--
-- Name: security_incidents security_incidents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.security_incidents
    ADD CONSTRAINT security_incidents_pkey PRIMARY KEY (id);


--
-- Name: slack_channel_context slack_channel_context_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.slack_channel_context
    ADD CONSTRAINT slack_channel_context_pkey PRIMARY KEY (id);


--
-- Name: slack_thread_memory slack_thread_memory_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.slack_thread_memory
    ADD CONSTRAINT slack_thread_memory_pkey PRIMARY KEY (id);


--
-- Name: smart_routing_log smart_routing_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.smart_routing_log
    ADD CONSTRAINT smart_routing_log_pkey PRIMARY KEY (id);


--
-- Name: telegram_chats telegram_chats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telegram_chats
    ADD CONSTRAINT telegram_chats_pkey PRIMARY KEY (id);


--
-- Name: telegram_integrations telegram_integrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telegram_integrations
    ADD CONSTRAINT telegram_integrations_pkey PRIMARY KEY (id);


--
-- Name: tenant_credentials tenant_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenant_credentials
    ADD CONSTRAINT tenant_credentials_pkey PRIMARY KEY (tenant_id);


--
-- Name: tenant_password_resets tenant_password_resets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenant_password_resets
    ADD CONSTRAINT tenant_password_resets_pkey PRIMARY KEY (id);


--
-- Name: tenant_subscriptions tenant_subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenant_subscriptions
    ADD CONSTRAINT tenant_subscriptions_pkey PRIMARY KEY (id);


--
-- Name: tenants tenants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);


--
-- Name: usage_logs usage_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usage_logs
    ADD CONSTRAINT usage_logs_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_agent_sessions_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_sessions_agent ON public.agent_sessions USING btree (agent_id);


--
-- Name: idx_agent_sessions_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_sessions_session_id ON public.agent_sessions USING btree (session_id);


--
-- Name: idx_agent_sessions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_sessions_status ON public.agent_sessions USING btree (status);


--
-- Name: idx_agent_sessions_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_sessions_tenant ON public.agent_sessions USING btree (tenant_id);


--
-- Name: idx_agent_sessions_websocket; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_sessions_websocket ON public.agent_sessions USING btree (websocket_id);


--
-- Name: idx_agent_tags_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_tags_category ON public.agent_tags USING btree (category);


--
-- Name: idx_agent_tags_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_tags_tenant ON public.agent_tags USING btree (tenant_id);


--
-- Name: idx_agents_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agents_active ON public.agents USING btree (is_active);


--
-- Name: idx_agents_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agents_email ON public.agents USING btree (email);


--
-- Name: idx_agents_invite_token; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agents_invite_token ON public.agents USING btree (invite_token);


--
-- Name: idx_agents_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agents_status ON public.agents USING btree (status);


--
-- Name: idx_agents_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agents_tenant ON public.agents USING btree (tenant_id);


--
-- Name: idx_backup_old_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_backup_old_id ON public.tenant_id_migration_backup USING btree (old_id);


--
-- Name: idx_chat_queue_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chat_queue_conversation ON public.chat_queue USING btree (conversation_id);


--
-- Name: idx_chat_queue_conversation_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_chat_queue_conversation_unique ON public.chat_queue USING btree (conversation_id);


--
-- Name: idx_chat_queue_position; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chat_queue_position ON public.chat_queue USING btree ("position");


--
-- Name: idx_chat_queue_priority; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chat_queue_priority ON public.chat_queue USING btree (priority);


--
-- Name: idx_chat_queue_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chat_queue_status ON public.chat_queue USING btree (status);


--
-- Name: idx_chat_queue_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chat_queue_tenant ON public.chat_queue USING btree (tenant_id);


--
-- Name: idx_chat_sessions_email_captured_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chat_sessions_email_captured_at ON public.chat_sessions USING btree (email_captured_at);


--
-- Name: idx_chat_sessions_email_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chat_sessions_email_expires_at ON public.chat_sessions USING btree (email_expires_at);


--
-- Name: idx_conversation_tagging_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversation_tagging_conversation ON public.conversation_tagging USING btree (conversation_id);


--
-- Name: idx_conversation_tagging_tag; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversation_tagging_tag ON public.conversation_tagging USING btree (tag_id);


--
-- Name: idx_instagram_conversations_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_instagram_conversations_conversation_id ON public.instagram_conversations USING btree (conversation_id);


--
-- Name: idx_instagram_conversations_integration; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_conversations_integration ON public.instagram_conversations USING btree (integration_id);


--
-- Name: idx_instagram_conversations_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_conversations_status ON public.instagram_conversations USING btree (conversation_status);


--
-- Name: idx_instagram_conversations_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_conversations_tenant ON public.instagram_conversations USING btree (tenant_id);


--
-- Name: idx_instagram_conversations_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_conversations_user ON public.instagram_conversations USING btree (instagram_user_id);


--
-- Name: idx_instagram_integrations_business_account; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_integrations_business_account ON public.instagram_integrations USING btree (instagram_business_account_id);


--
-- Name: idx_instagram_integrations_facebook_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_integrations_facebook_page ON public.instagram_integrations USING btree (facebook_page_id);


--
-- Name: idx_instagram_integrations_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_integrations_tenant_id ON public.instagram_integrations USING btree (tenant_id);


--
-- Name: idx_instagram_messages_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_messages_conversation ON public.instagram_messages USING btree (conversation_id);


--
-- Name: idx_instagram_messages_instagram_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_messages_instagram_id ON public.instagram_messages USING btree (instagram_message_id);


--
-- Name: idx_instagram_messages_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_messages_status ON public.instagram_messages USING btree (message_status);


--
-- Name: idx_instagram_messages_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_messages_tenant ON public.instagram_messages USING btree (tenant_id);


--
-- Name: idx_instagram_messages_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_messages_type ON public.instagram_messages USING btree (message_type);


--
-- Name: idx_instagram_messages_uuid; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_instagram_messages_uuid ON public.instagram_messages USING btree (message_uuid);


--
-- Name: idx_instagram_webhook_events_integration; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_webhook_events_integration ON public.instagram_webhook_events USING btree (integration_id);


--
-- Name: idx_instagram_webhook_events_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_webhook_events_status ON public.instagram_webhook_events USING btree (processing_status);


--
-- Name: idx_instagram_webhook_events_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_webhook_events_tenant ON public.instagram_webhook_events USING btree (tenant_id);


--
-- Name: idx_instagram_webhook_events_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_webhook_events_type ON public.instagram_webhook_events USING btree (event_type);


--
-- Name: idx_instagram_webhook_events_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instagram_webhook_events_user ON public.instagram_webhook_events USING btree (instagram_user_id);


--
-- Name: idx_knowledge_bases_crawl_schedule; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_knowledge_bases_crawl_schedule ON public.knowledge_bases USING btree (document_type, processing_status, last_crawled_at) WHERE (document_type = 'website'::public.documenttype);


--
-- Name: idx_knowledge_bases_processing_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_knowledge_bases_processing_status ON public.knowledge_bases USING btree (processing_status);


--
-- Name: idx_knowledge_bases_tenant_website; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_knowledge_bases_tenant_website ON public.knowledge_bases USING btree (tenant_id, document_type) WHERE (document_type = 'website'::public.documenttype);


--
-- Name: idx_live_chat_conversations_assigned_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_live_chat_conversations_assigned_agent ON public.live_chat_conversations USING btree (assigned_agent_id);


--
-- Name: idx_live_chat_conversations_customer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_live_chat_conversations_customer ON public.live_chat_conversations USING btree (customer_identifier);


--
-- Name: idx_live_chat_conversations_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_live_chat_conversations_session ON public.live_chat_conversations USING btree (chatbot_session_id);


--
-- Name: idx_live_chat_conversations_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_live_chat_conversations_status ON public.live_chat_conversations USING btree (status);


--
-- Name: idx_live_chat_conversations_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_live_chat_conversations_tenant ON public.live_chat_conversations USING btree (tenant_id);


--
-- Name: idx_live_chat_messages_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_live_chat_messages_agent ON public.live_chat_messages USING btree (agent_id);


--
-- Name: idx_live_chat_messages_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_live_chat_messages_conversation ON public.live_chat_messages USING btree (conversation_id);


--
-- Name: idx_live_chat_messages_sender_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_live_chat_messages_sender_type ON public.live_chat_messages USING btree (sender_type);


--
-- Name: idx_live_chat_messages_sent_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_live_chat_messages_sent_at ON public.live_chat_messages USING btree (sent_at);


--
-- Name: idx_live_chat_settings_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_live_chat_settings_tenant ON public.live_chat_settings USING btree (tenant_id);


--
-- Name: idx_pending_feedback_form_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pending_feedback_form_status ON public.pending_feedback USING btree (feedback_id, form_expired, form_accessed);


--
-- Name: idx_performance_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_performance_agent ON public.agent_tag_performance USING btree (agent_id);


--
-- Name: idx_performance_tag; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_performance_tag ON public.agent_tag_performance USING btree (tag_id);


--
-- Name: idx_routing_log_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_routing_log_conversation ON public.smart_routing_log USING btree (conversation_id);


--
-- Name: idx_routing_log_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_routing_log_tenant ON public.smart_routing_log USING btree (tenant_id);


--
-- Name: idx_security_incidents_risk_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_security_incidents_risk_type ON public.security_incidents USING btree (risk_type);


--
-- Name: idx_security_incidents_tenant_detected; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_security_incidents_tenant_detected ON public.security_incidents USING btree (tenant_id, detected_at);


--
-- Name: idx_slack_channel_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_slack_channel_tenant ON public.slack_channel_context USING btree (tenant_id, channel_id);


--
-- Name: idx_slack_thread_tenant_channel; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_slack_thread_tenant_channel ON public.slack_thread_memory USING btree (tenant_id, channel_id);


--
-- Name: idx_slack_thread_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_slack_thread_ts ON public.slack_thread_memory USING btree (thread_ts);


--
-- Name: idx_slack_thread_user_activity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_slack_thread_user_activity ON public.slack_thread_memory USING btree (user_id, last_activity);


--
-- Name: idx_telegram_chats_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_telegram_chats_active ON public.telegram_chats USING btree (is_active);


--
-- Name: idx_telegram_chats_chat_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_telegram_chats_chat_id ON public.telegram_chats USING btree (chat_id);


--
-- Name: idx_telegram_chats_integration; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_telegram_chats_integration ON public.telegram_chats USING btree (telegram_integration_id);


--
-- Name: idx_telegram_chats_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_telegram_chats_tenant ON public.telegram_chats USING btree (tenant_id);


--
-- Name: idx_telegram_chats_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_telegram_chats_user_id ON public.telegram_chats USING btree (user_id);


--
-- Name: idx_telegram_integrations_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_telegram_integrations_active ON public.telegram_integrations USING btree (is_active);


--
-- Name: idx_telegram_integrations_bot_username; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_telegram_integrations_bot_username ON public.telegram_integrations USING btree (bot_username);


--
-- Name: idx_telegram_integrations_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_telegram_integrations_tenant ON public.telegram_integrations USING btree (tenant_id);


--
-- Name: idx_tenants_business_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tenants_business_name ON public.tenants USING btree (business_name);


--
-- Name: ix_admins_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_admins_email ON public.admins USING btree (email);


--
-- Name: ix_admins_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_admins_id ON public.admins USING btree (id);


--
-- Name: ix_admins_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_admins_username ON public.admins USING btree (username);


--
-- Name: ix_agent_permission_overrides_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_permission_overrides_agent_id ON public.agent_permission_overrides USING btree (agent_id);


--
-- Name: ix_agent_permission_overrides_permission; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_permission_overrides_permission ON public.agent_permission_overrides USING btree (permission);


--
-- Name: ix_agent_role_history_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_role_history_agent_id ON public.agent_role_history USING btree (agent_id);


--
-- Name: ix_agent_role_history_changed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_role_history_changed_at ON public.agent_role_history USING btree (changed_at);


--
-- Name: ix_agents_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agents_role ON public.agents USING btree (role);


--
-- Name: ix_billing_history_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_billing_history_id ON public.billing_history USING btree (id);


--
-- Name: ix_booking_requests_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_booking_requests_id ON public.booking_requests USING btree (id);


--
-- Name: ix_chat_messages_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_messages_id ON public.chat_messages USING btree (id);


--
-- Name: ix_chat_sessions_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_sessions_id ON public.chat_sessions USING btree (id);


--
-- Name: ix_chat_sessions_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_chat_sessions_session_id ON public.chat_sessions USING btree (session_id);


--
-- Name: ix_chat_sessions_user_identifier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chat_sessions_user_identifier ON public.chat_sessions USING btree (user_identifier);


--
-- Name: ix_conversation_sessions_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversation_sessions_id ON public.conversation_sessions USING btree (id);


--
-- Name: ix_conversation_tags_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversation_tags_id ON public.conversation_tags USING btree (id);


--
-- Name: ix_conversation_transfers_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversation_transfers_id ON public.conversation_transfers USING btree (id);


--
-- Name: ix_conversations_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conversations_customer_id ON public.conversations USING btree (customer_id);


--
-- Name: ix_conversations_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_conversations_session_id ON public.conversations USING btree (session_id);


--
-- Name: ix_customer_devices_fingerprint; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_devices_fingerprint ON public.customer_devices USING btree (device_fingerprint);


--
-- Name: ix_customer_devices_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_devices_profile_id ON public.customer_devices USING btree (customer_profile_id);


--
-- Name: ix_customer_preferences_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_preferences_profile_id ON public.customer_preferences USING btree (customer_profile_id);


--
-- Name: ix_customer_profiles_customer_identifier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_profiles_customer_identifier ON public.customer_profiles USING btree (customer_identifier);


--
-- Name: ix_customer_profiles_tenant_customer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_profiles_tenant_customer ON public.customer_profiles USING btree (tenant_id, customer_identifier);


--
-- Name: ix_customer_sessions_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_sessions_profile_id ON public.customer_sessions USING btree (customer_profile_id);


--
-- Name: ix_customer_sessions_started_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_sessions_started_at ON public.customer_sessions USING btree (started_at);


--
-- Name: ix_faqs_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_faqs_id ON public.faqs USING btree (id);


--
-- Name: ix_instagram_conversations_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_instagram_conversations_conversation_id ON public.instagram_conversations USING btree (conversation_id);


--
-- Name: ix_instagram_conversations_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_conversations_id ON public.instagram_conversations USING btree (id);


--
-- Name: ix_instagram_conversations_instagram_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_conversations_instagram_user_id ON public.instagram_conversations USING btree (instagram_user_id);


--
-- Name: ix_instagram_conversations_integration_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_conversations_integration_id ON public.instagram_conversations USING btree (integration_id);


--
-- Name: ix_instagram_conversations_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_conversations_tenant_id ON public.instagram_conversations USING btree (tenant_id);


--
-- Name: ix_instagram_integrations_facebook_page_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_integrations_facebook_page_id ON public.instagram_integrations USING btree (facebook_page_id);


--
-- Name: ix_instagram_integrations_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_integrations_id ON public.instagram_integrations USING btree (id);


--
-- Name: ix_instagram_integrations_instagram_business_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_integrations_instagram_business_account_id ON public.instagram_integrations USING btree (instagram_business_account_id);


--
-- Name: ix_instagram_integrations_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_instagram_integrations_tenant_id ON public.instagram_integrations USING btree (tenant_id);


--
-- Name: ix_instagram_messages_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_messages_conversation_id ON public.instagram_messages USING btree (conversation_id);


--
-- Name: ix_instagram_messages_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_messages_id ON public.instagram_messages USING btree (id);


--
-- Name: ix_instagram_messages_instagram_message_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_messages_instagram_message_id ON public.instagram_messages USING btree (instagram_message_id);


--
-- Name: ix_instagram_messages_message_uuid; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_instagram_messages_message_uuid ON public.instagram_messages USING btree (message_uuid);


--
-- Name: ix_instagram_messages_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_messages_tenant_id ON public.instagram_messages USING btree (tenant_id);


--
-- Name: ix_instagram_webhook_events_event_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_webhook_events_event_id ON public.instagram_webhook_events USING btree (event_id);


--
-- Name: ix_instagram_webhook_events_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_webhook_events_event_type ON public.instagram_webhook_events USING btree (event_type);


--
-- Name: ix_instagram_webhook_events_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_webhook_events_id ON public.instagram_webhook_events USING btree (id);


--
-- Name: ix_instagram_webhook_events_instagram_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_webhook_events_instagram_user_id ON public.instagram_webhook_events USING btree (instagram_user_id);


--
-- Name: ix_instagram_webhook_events_integration_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_webhook_events_integration_id ON public.instagram_webhook_events USING btree (integration_id);


--
-- Name: ix_instagram_webhook_events_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instagram_webhook_events_tenant_id ON public.instagram_webhook_events USING btree (tenant_id);


--
-- Name: ix_knowledge_bases_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_knowledge_bases_id ON public.knowledge_bases USING btree (id);


--
-- Name: ix_knowledge_bases_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_knowledge_bases_name ON public.knowledge_bases USING btree (name);


--
-- Name: ix_live_chats_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_live_chats_id ON public.live_chats USING btree (id);


--
-- Name: ix_live_chats_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_live_chats_session_id ON public.live_chats USING btree (session_id);


--
-- Name: ix_live_chats_user_identifier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_live_chats_user_identifier ON public.live_chats USING btree (user_identifier);


--
-- Name: ix_password_resets_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_password_resets_id ON public.password_resets USING btree (id);


--
-- Name: ix_password_resets_token; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_password_resets_token ON public.password_resets USING btree (token);


--
-- Name: ix_pending_feedback_feedback_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_pending_feedback_feedback_id ON public.pending_feedback USING btree (feedback_id);


--
-- Name: ix_pending_feedback_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_feedback_id ON public.pending_feedback USING btree (id);


--
-- Name: ix_pricing_plans_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pricing_plans_id ON public.pricing_plans USING btree (id);


--
-- Name: ix_pricing_plans_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_pricing_plans_name ON public.pricing_plans USING btree (name);


--
-- Name: ix_pricing_plans_plan_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pricing_plans_plan_type ON public.pricing_plans USING btree (plan_type);


--
-- Name: ix_scraped_emails_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scraped_emails_email ON public.scraped_emails USING btree (email);


--
-- Name: ix_scraped_emails_email_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_scraped_emails_email_hash ON public.scraped_emails USING btree (email_hash);


--
-- Name: ix_scraped_emails_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scraped_emails_id ON public.scraped_emails USING btree (id);


--
-- Name: ix_slack_channel_context_channel_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_slack_channel_context_channel_id ON public.slack_channel_context USING btree (channel_id);


--
-- Name: ix_slack_channel_context_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_slack_channel_context_id ON public.slack_channel_context USING btree (id);


--
-- Name: ix_slack_channel_context_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_slack_channel_context_tenant_id ON public.slack_channel_context USING btree (tenant_id);


--
-- Name: ix_slack_thread_memory_channel_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_slack_thread_memory_channel_id ON public.slack_thread_memory USING btree (channel_id);


--
-- Name: ix_slack_thread_memory_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_slack_thread_memory_id ON public.slack_thread_memory USING btree (id);


--
-- Name: ix_slack_thread_memory_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_slack_thread_memory_tenant_id ON public.slack_thread_memory USING btree (tenant_id);


--
-- Name: ix_slack_thread_memory_thread_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_slack_thread_memory_thread_ts ON public.slack_thread_memory USING btree (thread_ts);


--
-- Name: ix_slack_thread_memory_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_slack_thread_memory_user_id ON public.slack_thread_memory USING btree (user_id);


--
-- Name: ix_telegram_chats_chat_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_telegram_chats_chat_id ON public.telegram_chats USING btree (chat_id);


--
-- Name: ix_telegram_chats_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_telegram_chats_id ON public.telegram_chats USING btree (id);


--
-- Name: ix_telegram_chats_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_telegram_chats_tenant_id ON public.telegram_chats USING btree (tenant_id);


--
-- Name: ix_telegram_chats_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_telegram_chats_user_id ON public.telegram_chats USING btree (user_id);


--
-- Name: ix_telegram_integrations_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_telegram_integrations_id ON public.telegram_integrations USING btree (id);


--
-- Name: ix_telegram_integrations_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_telegram_integrations_tenant_id ON public.telegram_integrations USING btree (tenant_id);


--
-- Name: ix_tenant_password_resets_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tenant_password_resets_id ON public.tenant_password_resets USING btree (id);


--
-- Name: ix_tenant_password_resets_token; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_tenant_password_resets_token ON public.tenant_password_resets USING btree (token);


--
-- Name: ix_tenant_subscriptions_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tenant_subscriptions_id ON public.tenant_subscriptions USING btree (id);


--
-- Name: ix_tenants_api_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_tenants_api_key ON public.tenants USING btree (api_key);


--
-- Name: ix_tenants_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_tenants_email ON public.tenants USING btree (email);


--
-- Name: ix_tenants_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tenants_id ON public.tenants USING btree (id);


--
-- Name: ix_tenants_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_tenants_name ON public.tenants USING btree (name);


--
-- Name: ix_tenants_supabase_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tenants_supabase_user_id ON public.tenants USING btree (supabase_user_id);


--
-- Name: ix_usage_logs_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_usage_logs_id ON public.usage_logs USING btree (id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_id ON public.users USING btree (id);


--
-- Name: ix_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);


--
-- Name: agent_permission_overrides agent_permission_overrides_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_permission_overrides
    ADD CONSTRAINT agent_permission_overrides_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.agents(id);


--
-- Name: agent_permission_overrides agent_permission_overrides_granted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_permission_overrides
    ADD CONSTRAINT agent_permission_overrides_granted_by_fkey FOREIGN KEY (granted_by) REFERENCES public.agents(id);


--
-- Name: agent_role_history agent_role_history_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_role_history
    ADD CONSTRAINT agent_role_history_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.agents(id);


--
-- Name: agent_role_history agent_role_history_changed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_role_history
    ADD CONSTRAINT agent_role_history_changed_by_fkey FOREIGN KEY (changed_by) REFERENCES public.agents(id);


--
-- Name: agent_sessions agent_sessions_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_sessions
    ADD CONSTRAINT agent_sessions_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: agent_tag_performance agent_tag_performance_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tag_performance
    ADD CONSTRAINT agent_tag_performance_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.agents(id);


--
-- Name: agent_tag_performance agent_tag_performance_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tag_performance
    ADD CONSTRAINT agent_tag_performance_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.agent_tags(id);


--
-- Name: agent_tags_association agent_tags_association_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tags_association
    ADD CONSTRAINT agent_tags_association_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.agents(id);


--
-- Name: agent_tags_association agent_tags_association_assigned_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tags_association
    ADD CONSTRAINT agent_tags_association_assigned_by_fkey FOREIGN KEY (assigned_by) REFERENCES public.agents(id);


--
-- Name: agent_tags_association agent_tags_association_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tags_association
    ADD CONSTRAINT agent_tags_association_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.agent_tags(id);


--
-- Name: agent_tags agent_tags_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_tags
    ADD CONSTRAINT agent_tags_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.agents(id);


--
-- Name: billing_history billing_history_subscription_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.billing_history
    ADD CONSTRAINT billing_history_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES public.tenant_subscriptions(id);


--
-- Name: booking_requests booking_requests_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.booking_requests
    ADD CONSTRAINT booking_requests_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(session_id);


--
-- Name: chat_messages chat_messages_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_messages
    ADD CONSTRAINT chat_messages_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(id);


--
-- Name: chat_queue chat_queue_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_queue
    ADD CONSTRAINT chat_queue_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.live_chat_conversations(id) ON DELETE CASCADE;


--
-- Name: chat_queue chat_queue_preferred_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_queue
    ADD CONSTRAINT chat_queue_preferred_agent_id_fkey FOREIGN KEY (preferred_agent_id) REFERENCES public.agents(id);


--
-- Name: conversation_tagging conversation_tagging_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_tagging
    ADD CONSTRAINT conversation_tagging_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.live_chat_conversations(id);


--
-- Name: conversation_tagging conversation_tagging_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_tagging
    ADD CONSTRAINT conversation_tagging_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.live_chat_messages(id);


--
-- Name: conversation_tagging conversation_tagging_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_tagging
    ADD CONSTRAINT conversation_tagging_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.agent_tags(id);


--
-- Name: conversation_tagging conversation_tagging_verified_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation_tagging
    ADD CONSTRAINT conversation_tagging_verified_by_fkey FOREIGN KEY (verified_by) REFERENCES public.agents(id);


--
-- Name: customer_devices customer_devices_customer_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_devices
    ADD CONSTRAINT customer_devices_customer_profile_id_fkey FOREIGN KEY (customer_profile_id) REFERENCES public.customer_profiles(id) ON DELETE CASCADE;


--
-- Name: customer_preferences customer_preferences_customer_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_preferences
    ADD CONSTRAINT customer_preferences_customer_profile_id_fkey FOREIGN KEY (customer_profile_id) REFERENCES public.customer_profiles(id) ON DELETE CASCADE;


--
-- Name: customer_sessions customer_sessions_customer_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_sessions
    ADD CONSTRAINT customer_sessions_customer_profile_id_fkey FOREIGN KEY (customer_profile_id) REFERENCES public.customer_profiles(id) ON DELETE CASCADE;


--
-- Name: agents fk_agents_promoted_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agents
    ADD CONSTRAINT fk_agents_promoted_by FOREIGN KEY (promoted_by) REFERENCES public.agents(id);


--
-- Name: instagram_conversations instagram_conversations_integration_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instagram_conversations
    ADD CONSTRAINT instagram_conversations_integration_id_fkey FOREIGN KEY (integration_id) REFERENCES public.instagram_integrations(id);


--
-- Name: instagram_messages instagram_messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instagram_messages
    ADD CONSTRAINT instagram_messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.instagram_conversations(id);


--
-- Name: instagram_webhook_events instagram_webhook_events_integration_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instagram_webhook_events
    ADD CONSTRAINT instagram_webhook_events_integration_id_fkey FOREIGN KEY (integration_id) REFERENCES public.instagram_integrations(id);


--
-- Name: live_chat_conversations live_chat_conversations_assigned_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_chat_conversations
    ADD CONSTRAINT live_chat_conversations_assigned_agent_id_fkey FOREIGN KEY (assigned_agent_id) REFERENCES public.agents(id);


--
-- Name: live_chat_conversations live_chat_conversations_previous_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_chat_conversations
    ADD CONSTRAINT live_chat_conversations_previous_agent_id_fkey FOREIGN KEY (previous_agent_id) REFERENCES public.agents(id);


--
-- Name: live_chat_messages live_chat_messages_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_chat_messages
    ADD CONSTRAINT live_chat_messages_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.agents(id);


--
-- Name: live_chat_messages live_chat_messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_chat_messages
    ADD CONSTRAINT live_chat_messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.live_chat_conversations(id) ON DELETE CASCADE;


--
-- Name: live_chat_messages live_chat_messages_reply_to_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.live_chat_messages
    ADD CONSTRAINT live_chat_messages_reply_to_message_id_fkey FOREIGN KEY (reply_to_message_id) REFERENCES public.live_chat_messages(id);


--
-- Name: messages messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id);


--
-- Name: password_resets password_resets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_resets
    ADD CONSTRAINT password_resets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: pending_feedback pending_feedback_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_feedback
    ADD CONSTRAINT pending_feedback_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(session_id);


--
-- Name: scraped_emails scraped_emails_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scraped_emails
    ADD CONSTRAINT scraped_emails_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(session_id);


--
-- Name: scraped_emails scraped_emails_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scraped_emails
    ADD CONSTRAINT scraped_emails_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: smart_routing_log smart_routing_log_assigned_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.smart_routing_log
    ADD CONSTRAINT smart_routing_log_assigned_agent_id_fkey FOREIGN KEY (assigned_agent_id) REFERENCES public.agents(id);


--
-- Name: smart_routing_log smart_routing_log_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.smart_routing_log
    ADD CONSTRAINT smart_routing_log_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.live_chat_conversations(id);


--
-- Name: telegram_chats telegram_chats_telegram_integration_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telegram_chats
    ADD CONSTRAINT telegram_chats_telegram_integration_id_fkey FOREIGN KEY (telegram_integration_id) REFERENCES public.telegram_integrations(id);


--
-- Name: tenant_subscriptions tenant_subscriptions_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenant_subscriptions
    ADD CONSTRAINT tenant_subscriptions_plan_id_fkey FOREIGN KEY (plan_id) REFERENCES public.pricing_plans(id);


--
-- Name: usage_logs usage_logs_subscription_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usage_logs
    ADD CONSTRAINT usage_logs_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES public.tenant_subscriptions(id);


--
-- PostgreSQL database dump complete
--

