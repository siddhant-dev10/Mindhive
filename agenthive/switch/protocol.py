"""Switch Agent Protocol Constants and API Routes."""

# Official Switch Agent Protocol Endpoints
REGISTER_AGENT_ENDPOINT = "/switch/api/v1/agents/register"
AGENT_EVENTS_ENDPOINT = "/switch/api/v1/agents/{agent_id}/events"
AGENT_HEARTBEAT_ENDPOINT = "/switch/api/v1/connection/beat"
ROOMS_ENDPOINT = "/switch/api/v1/rooms"
ROOM_MESSAGES_ENDPOINT = "/switch/api/v1/rooms/{room_id}/messages"
ROOM_EVENTS_ENDPOINT = "/switch/api/v1/rooms/{room_id}/events"
