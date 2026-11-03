"""Cliente REST de la API de Gemini (multimodal)."""
import base64
import requests

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiError(Exception):
    pass


class GeminiClient:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def generate(self, prompt: str, images=()):
        """images: iterable de (bytes, mime). Devuelve texto."""
        if not self.api_key:
            raise GeminiError("Falta GEMINI_API_KEY.")
        parts = [{"text": prompt}]
        for data, mime in images:
            parts.append({"inline_data": {
                "mime_type": mime,
                "data": base64.b64encode(data).decode(),
            }})
        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.2},
        }
        try:
            r = requests.post(
                ENDPOINT.format(model=self.model),
                headers={"x-goog-api-key": self.api_key},
                json=body,
                timeout=55,
            )
        except requests.RequestException as e:
            raise GeminiError(f"Error de red con Gemini: {e}")
        if r.status_code == 429:
            raise GeminiError("Se alcanzó el límite del nivel gratuito de Gemini. Probá en unos minutos.")
        if r.status_code != 200:
            raise GeminiError(f"Gemini devolvió {r.status_code}: {r.text[:200]}")
        try:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError):
            raise GeminiError("Gemini no devolvió texto (posible bloqueo de seguridad).")
