"""Unit and integration tests for Gemini Conversational Service."""

import pytest
import unittest.mock as mock
from agenthive.services.gemini_service import (
    GeminiConversationalService,
    ConversationSession,
    ENGINEERING_MANAGER_SYSTEM_PROMPT,
)
from agenthive.services.github_service import CodebaseInventory


def _create_sample_inventory() -> CodebaseInventory:
    return CodebaseInventory(
        repo_name="sample-project",
        owner="test-owner",
        is_local=True,
        description="A robust sample asynchronous service.",
        default_branch="main",
        stars=10,
        open_issues=2,
        languages={"Python": 12},
        primary_language="Python",
        frameworks=["FastAPI", "Discord.py", "SQLite (WAL)"],
        entry_points=["main.py"],
        manifests={"requirements.txt": "fastapi\nuvicorn\n"},
        file_tree=["main.py", "requirements.txt", "README.md"],
        readme_content="# Sample Project\nAn async project for testing.",
        architecture_overview="Multi-tiered Service (Python) with FastAPI.",
        engineering_assessment={
            "existing_functionality": ["FastAPI REST endpoints"],
            "incomplete_functionality": ["Missing CI pipeline"],
            "security_and_debt": ["Ensure secret redaction"],
            "testing_state": ["Standard tests detected"],
        },
        improvement_recommendations=[
            {
                "priority": "P0 (Highest)",
                "title": "Establish Multi-Agent Workflow",
                "rationale": "Align agents over Switch.",
                "estimated_complexity": "Medium (2 hours)",
                "responsible_agent": "Nous Hermes",
                "dependencies": [],
            }
        ],
        file_citations={"main.py": "from fastapi import FastAPI"},
    )


@pytest.mark.asyncio
async def test_gemini_not_configured():
    svc = GeminiConversationalService()
    svc.api_key = ""
    svc.sdk_client = None

    assert not svc.is_configured
    status = await svc.check_availability()
    assert not status["available"]
    assert "not configured" in status["reason"]

    reply = await svc.chat("session-1", "Hello")
    assert "Conversational AI Offline" in reply
    assert "GEMINI_API_KEY" in reply


def test_conversation_session_turns_and_sliding_window():
    session = ConversationSession("session-test")
    assert len(session.history) == 0

    # Add 25 turns
    for i in range(25):
        session.add_turn("user" if i % 2 == 0 else "model", f"Turn {i}")

    # History capped at 20 turns
    assert len(session.history) == 20
    assert session.history[-1]["parts"][0]["text"] == "Turn 24"


@pytest.mark.asyncio
async def test_gemini_chat_with_mocked_sdk():
    svc = GeminiConversationalService()
    svc.api_key = "test-live-key"

    mock_client = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.text = "Hello! I am MindHive, ready to coordinate your agents."
    mock_client.models.generate_content.return_value = mock_response
    svc.sdk_client = mock_client

    reply = await svc.chat("session-2", "Who are you?")
    assert "MindHive" in reply
    session = svc.sessions["session-2"]
    assert len(session.history) == 2
    assert session.history[0]["parts"][0]["text"] == "Who are you?"
    assert session.history[1]["parts"][0]["text"] == reply


@pytest.mark.asyncio
async def test_gemini_chat_with_mocked_rest():
    svc = GeminiConversationalService()
    svc.api_key = "test-live-key"
    svc.sdk_client = None  # Force REST path

    mock_json = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Observed architecture: FastAPI backend with SQLite."}]
                }
            }
        ]
    }

    with mock.patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_json
        mock_post.return_value = mock_resp

        inv = _create_sample_inventory()
        reply = await svc.chat("session-3", "Analyze architecture", codebase_inventory=inv)
        assert "Observed architecture" in reply
        assert mock_post.called


@pytest.mark.asyncio
async def test_gemini_secret_redaction():
    svc = GeminiConversationalService()
    svc.api_key = "test-live-key"

    mock_client = mock.MagicMock()
    mock_response = mock.MagicMock()
    # Mock LLM echoing a secret token
    mock_response.text = "Here is the key: ghp_1234567890abcdefghijklmnopqrstuvwxyz"
    mock_client.models.generate_content.return_value = mock_response
    svc.sdk_client = mock_client

    reply = await svc.chat("session-sec", "Give me token")
    assert "ghp_" not in reply
    assert "[REDACTED" in reply


def test_deterministic_codebase_explanation():
    svc = GeminiConversationalService()
    inv = _create_sample_inventory()
    explanation = svc.explain_codebase_deterministic(inv)

    assert inv.repo_name in explanation
    assert "Technical Architecture" in explanation
    assert "Observed Capabilities" in explanation
    assert "Recommended Development Workflow" in explanation
    assert "Establish Multi-Agent Workflow" in explanation
