"""Cliente mínimo de la Bot API de Telegram (solo requests)."""
import requests

MAX_LEN = 4000


class TelegramClient:
    def __init__(self, token: str):
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}"

    def _post(self, method: str, **payload):
        r = requests.post(f"{self.base}/{method}", json=payload, timeout=20)
        r.raise_for_status()
        return r.json()

    def send_message(self, chat_id, text, reply_markup=None, reply_to=None):
        """Envía texto plano; parte los mensajes largos."""
        chunks = [text[i:i + MAX_LEN] for i in range(0, len(text), MAX_LEN)] or [""]
        for i, chunk in enumerate(chunks):
            payload = {"chat_id": chat_id, "text": chunk}
            if reply_markup and i == len(chunks) - 1:
                payload["reply_markup"] = reply_markup
            if reply_to and i == 0:
                payload["reply_to_message_id"] = reply_to
            self._post("sendMessage", **payload)

    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text[:MAX_LEN]}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        self._post("editMessageText", **payload)

    def answer_callback(self, callback_id, text=""):
        self._post("answerCallbackQuery", callback_query_id=callback_id, text=text)

    def send_action(self, chat_id, action="typing"):
        self._post("sendChatAction", chat_id=chat_id, action=action)

    def download_file(self, file_id):
        """Devuelve (bytes, mime)."""
        info = self._post("getFile", file_id=file_id)["result"]
        path = info["file_path"]
        r = requests.get(
            f"https://api.telegram.org/file/bot{self.token}/{path}", timeout=30
        )
        r.raise_for_status()
        mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
        return r.content, mime
