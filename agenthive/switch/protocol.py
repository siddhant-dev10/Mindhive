"""Switch Agent Protocol Constants and API Routes.

Defines wire protocol endpoints for both:
1. Official Switch Infrastructure (ghcr.io/sandbox-quantum/switch-core / https://docs.switchagents.ai/)
2. Local Protocol Reference Bridge (offline / zero-dependency fallback)
"""

# ==============================================================================
# 1. Official Switch Core API Endpoints (sandbox-quantum/switch)
# ==============================================================================
OFFICIAL_HEALTH_READY = "/health/ready"
OFFICIAL_VERSION = "/version"

# Agent lifecycle & registration
OFFICIAL_REGISTER_AGENT = "/agents"
OFFICIAL_REGISTER_KNOWN = "/agents/register-known"
OFFICIAL_REGISTER_KNOWN_BULK = "/agents/register-known-bulk"

# Real-time event streaming & connection presence (SSE / Long Poll)
OFFICIAL_AGENT_EVENTS = "/agents/{agent_id}/events"
OFFICIAL_CONNECTION_BEAT = "/agents/{agent_id}/connection/beat"
OFFICIAL_CONNECTION_SUBSCRIBE = "/agents/{agent_id}/connection/subscribe"
OFFICIAL_CONNECTION_UNSUBSCRIBE = "/agents/{agent_id}/connection/unsubscribe"

# Messaging & collaboration rooms
OFFICIAL_AGENT_MESSAGE = "/agents/{agent_id}/message"
OFFICIAL_MODERATION_ROOMS = "/agents/{agent_id}/moderation/rooms"
OFFICIAL_ROOM_HISTORY = "/agents/{agent_id}/rooms/{room_id}/history"
OFFICIAL_ROOM_PARTICIPANTS = "/agents/rooms/{room_id}/participants"

# Sessions and mediation
OFFICIAL_SESSION_ACTIVITY = "/agent-sessions/{session_id}/activity"
OFFICIAL_SESSION_APPROVALS = "/agent-sessions/{session_id}/approvals"

# ==============================================================================
# 2. Local Protocol Reference Bridge Endpoints (Backward Compatible Fallback)
# ==============================================================================
LOCAL_PREFIX = "/switch/api/v1"
REGISTER_AGENT_ENDPOINT = "/switch/api/v1/agents/register"
AGENT_EVENTS_ENDPOINT = "/switch/api/v1/agents/{agent_id}/events"
AGENT_HEARTBEAT_ENDPOINT = "/switch/api/v1/connection/beat"
ROOMS_ENDPOINT = "/switch/api/v1/rooms"
ROOM_MESSAGES_ENDPOINT = "/switch/api/v1/rooms/{room_id}/messages"
ROOM_EVENTS_ENDPOINT = "/switch/api/v1/rooms/{room_id}/events"
