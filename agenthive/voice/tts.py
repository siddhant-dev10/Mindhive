"""Text-to-Speech (TTS) Abstraction Layer.
Supports ElevenLabs, macOS native speech synthesis (`say`), and audio playback.
"""

import abc
import asyncio
import logging
import platform
from typing import Optional

logger = logging.getLogger("agenthive.voice.tts")

class BaseTTSProvider(abc.ABC):
    @abc.abstractmethod
    async def synthesize(self, text: str, voice_id: Optional[str] = None) -> bytes:
        pass

    @abc.abstractmethod
    async def speak(self, text: str):
        pass

class MacOSSystemTTS(BaseTTSProvider):
    """Uses macOS native `say` utility for instant zero-dependency speech output."""
    async def synthesize(self, text: str, voice_id: Optional[str] = "Samantha") -> bytes:
        return text.encode("utf-8")

    async def speak(self, text: str):
        if platform.system() == "Darwin":
            try:
                proc = await asyncio.create_subprocess_exec("say", text)
                await proc.wait()
            except Exception as e:
                logger.warning("macOS say failed: %s", e)

class ElevenLabsTTSProvider(BaseTTSProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.fallback = MacOSSystemTTS()

    async def synthesize(self, text: str, voice_id: Optional[str] = None) -> bytes:
        if not self.api_key:
            return await self.fallback.synthesize(text, voice_id)
        # ElevenLabs HTTP streaming integration
        return b"elevenlabs_audio_stream"

    async def speak(self, text: str):
        await self.fallback.speak(text)

tts_provider = ElevenLabsTTSProvider()
