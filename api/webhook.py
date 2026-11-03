"""Entrada de Vercel (función serverless). Telegram llama acá por webhook."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.config import Config  # noqa: E402
from bot.gemini_client import GeminiClient  # noqa: E402
from bot.handlers import process_update  # noqa: E402
from bot.telegram_api import TelegramClient  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _reply(self, code, body="ok"):
        self.send_response(code)
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        self._reply(200, "stroke-bot activo")

    def do_POST(self):
        cfg = Config.from_env()
        # Solo Telegram conoce el secreto configurado al registrar el webhook.
        secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not cfg.webhook_secret or secret != cfg.webhook_secret:
            self._reply(403, "forbidden")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            update = json.loads(self.rfile.read(length) or b"{}")
            process_update(
                update,
                TelegramClient(cfg.telegram_token),
                GeminiClient(cfg.gemini_api_key, cfg.gemini_model),
                cfg,
            )
        except Exception as e:  # nunca devolver 5xx: Telegram reintentaría sin fin
            print(f"error procesando update: {e!r}")
        self._reply(200)
