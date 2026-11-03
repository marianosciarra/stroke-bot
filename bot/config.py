"""Configuración leída de variables de entorno (nunca hardcodear tokens)."""
import os
from dataclasses import dataclass, field


@dataclass
class Config:
    telegram_token: str = ""
    webhook_secret: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    allowed_user_ids: set = field(default_factory=set)

    @classmethod
    def from_env(cls) -> "Config":
        ids = set()
        for part in os.environ.get("ALLOWED_USER_IDS", "").split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
        return cls(
            telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            webhook_secret=os.environ.get("TELEGRAM_WEBHOOK_SECRET", ""),
            gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
            allowed_user_ids=ids,
        )
