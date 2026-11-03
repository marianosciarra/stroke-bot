"""Registra el webhook de Telegram. Uso:
  TELEGRAM_BOT_TOKEN=... TELEGRAM_WEBHOOK_SECRET=... python scripts/set_webhook.py https://TU-PROYECTO.vercel.app/api/webhook
"""
import os
import sys

import requests

url = sys.argv[1]
token = os.environ["TELEGRAM_BOT_TOKEN"]
secret = os.environ["TELEGRAM_WEBHOOK_SECRET"]
r = requests.post(
    f"https://api.telegram.org/bot{token}/setWebhook",
    json={"url": url, "secret_token": secret, "allowed_updates": ["message", "callback_query"]},
    timeout=20,
)
print(r.status_code, r.text)
