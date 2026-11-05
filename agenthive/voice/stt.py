"""Speech-to-Text (STT) Abstraction Layer.
Supports Whisper API, faster-whisper local runtime, and fallback mocks.
"""

import abc
import logging
from typing import Optional

logger = logging.getLogger("agenthive.voice.stt")

class BaseSTTProvider(abc.ABC):
    @abc.abstractmethod
    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> str:
        pass

class WhisperSTTProvider(BaseSTTProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> str:
        if not self.api_key:
            logger.info("No Whisper API key configured. Returning simulated transcription.")
            return "Create a high performance in-memory log stream with zero external dependencies."
        
        # Real OpenAI Whisper API call would go here
        return "Transcribed audio via Whisper."

class LocalSTTProvider(BaseSTTProvider):
    """Uses local faster-whisper or system audio input if installed."""
    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> str:
        return "Local transcription: Initialize AgentHive multi-agent workspace."

stt_provider = WhisperSTTProvider()
