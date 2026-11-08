"""Tests for Discord Conversational Interface, Dispatcher Routing, and Human-in-the-Loop Gate."""

import pytest
import unittest.mock as mock
from agenthive.config import settings
from agenthive.discord_gateway.dispatcher import discord_dispatcher
from agenthive.discord_gateway.bot import AgentHiveDiscordBot, HAS_DISCORD_LIB


@pytest.mark.asyncio
async def test_conversational_greeting():
    res = await discord_dispatcher.handle_conversational_message(
        text="hello",
        user_id="test-user-1",
        context_id="test-channel-1",
    )
    assert res["success"]
    assert res["intent"] == "greeting"
    assert "MindHive" in res["response_text"]
    assert "Switch" in res["response_text"]
    assert "Codex" in res["response_text"]
    assert not res["requires_approval"]


@pytest.mark.asyncio
async def test_conversational_repo_analysis():
    # Ask MindHive to analyze local workspace
    res = await discord_dispatcher.handle_conversational_message(
        text="what does this project do?",
        user_id="test-user-1",
        context_id="test-channel-2",
    )
    assert res["success"]
    assert res["intent"] == "repo_analysis"
    assert res["repo_inventory"] is not None
    assert "Architecture" in res["response_text"] or "Codebase Analysis" in res["response_text"]
    assert not res["requires_approval"]


@pytest.mark.asyncio
async def test_workflow_proposal_unauthorized_user():
    # Non-owner user attempting to create a development plan
    res = await discord_dispatcher.handle_conversational_message(
        text="create a development plan for this codebase",
        user_id="unauthorized-intruder",
        context_id="test-channel-3",
    )
    assert not res["success"]
    assert res["intent"] == "workflow_proposal"
    assert "Authorization Denied" in res["response_text"]
    assert not res["requires_approval"]


@pytest.mark.asyncio
async def test_workflow_proposal_authorized_owner_flow():
    # Authorized owner triggers development plan
    owner_id = settings.discord_owner_id or "test-owner"
    res = await discord_dispatcher.handle_conversational_message(
        text="create a development plan and propose next tasks",
        user_id=owner_id,
        context_id="test-channel-4",
    )
    assert res["success"]
    assert res["intent"] == "workflow_proposal"
    assert res["requires_approval"] is True
    assert res["project_id"] is not None
    assert res["project_id"] != "4d633575-798c-4737-93c1-0dfbcd63db1b"  # Acceptance project untouched
    assert res["switch_room_id"] is not None
    assert "WBS" in res["response_text"] or "Work Breakdown Structure" in res["response_text"]
    assert "Sovereign Human Approval Gate Active" in res["response_text"]
    assert "plan" in res
    assert len(res["plan"]["tasks"]) > 0


def test_discord_bot_message_chunking():
    bot = AgentHiveDiscordBot()
    short_text = "Hello world"
    chunks = bot._chunk_text(short_text, limit=100)
    assert chunks == ["Hello world"]

    # 350 characters split with limit 100
    long_text = "\n".join([f"Line {i}: This is some structured log output." for i in range(15)])
    chunks = bot._chunk_text(long_text, limit=100)
    assert len(chunks) > 1
    assert all(len(c) <= 120 for c in chunks)


def test_discord_bot_deduplication():
    bot = AgentHiveDiscordBot()
    bot._processed_messages[101] = 1000.0
    bot._processed_messages[102] = 2000.0

    # With now = 2050.0, 101 is > 60s old, 102 is <= 60s old
    with mock.patch("time.monotonic", return_value=2050.0):
        bot._cleanup_processed_messages(ttl_seconds=60.0)
        assert 101 not in bot._processed_messages
        assert 102 in bot._processed_messages


@pytest.mark.asyncio
async def test_discord_on_message_ignores_bots_and_self():
    if not HAS_DISCORD_LIB:
        pytest.skip("discord.py not installed")

    bot = AgentHiveDiscordBot()
    bot_user = mock.MagicMock()
    bot_user.id = 9999

    with mock.patch.object(AgentHiveDiscordBot, "user", new_callable=mock.PropertyMock, return_value=bot_user):
        # Case 1: Message from another bot
        msg_bot = mock.MagicMock()
        msg_bot.author.bot = True
        msg_bot.author.id = 1234
        with mock.patch.object(discord_dispatcher, "handle_conversational_message") as mock_disp:
            await bot.on_message(msg_bot)
            assert not mock_disp.called

        # Case 2: Message from self
        msg_self = mock.MagicMock()
        msg_self.author.bot = False
        msg_self.author.id = 9999
        with mock.patch.object(discord_dispatcher, "handle_conversational_message") as mock_disp:
            await bot.on_message(msg_self)
            assert not mock_disp.called

        # Case 3: Message in channel without mention
        msg_no_mention = mock.MagicMock()
        msg_no_mention.author.bot = False
        msg_no_mention.author.id = 5678
        msg_no_mention.mentions = []
        msg_no_mention.channel = mock.MagicMock()
        with mock.patch.object(discord_dispatcher, "handle_conversational_message") as mock_disp:
            await bot.on_message(msg_no_mention)
            assert not mock_disp.called
