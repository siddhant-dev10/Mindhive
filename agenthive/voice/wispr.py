"""Wispr Flow Integration & Voice Direction Guide for AgentHive.
Wispr Flow provides ultra-fast speech-to-text dictation that operates system-wide on macOS.
"""

from pathlib import Path
import os
import logging

logger = logging.getLogger("agenthive.voice.wispr")

WISPR_APP_PATH = Path("/Applications/Wispr Flow.app")

class WisprFlowIntegration:
    def is_installed(self) -> bool:
        return WISPR_APP_PATH.exists()

    def get_status(self) -> dict:
        installed = self.is_installed()
        return {
            "app_name": "Wispr Flow",
            "path": str(WISPR_APP_PATH),
            "installed": installed,
            "status": "Available" if installed else "Not Found",
            "usage": (
                "Hold the Wispr Flow activation hotkey (Fn / Custom hotkey) to speak project descriptions, "
                "issue Discord slash commands like '/newproject', or dictate revision feedback directly into AgentHive."
            )
        }

wispr_integration = WisprFlowIntegration()
