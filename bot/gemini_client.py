"""Cliente REST de la API de Gemini (multimodal) con conmutación rápida entre
modelos: si uno está saturado, sin cuota o retirado, pasa al siguiente sin
esperar. `model` puede ser una lista separada por comas (orden de preferencia)."""
import base64
import time

import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"
ENDPOINT = BASE + "/models/{model}:generateContent"

# Errores por modelo: se salta al siguiente modelo de inmediato.
SWITCH_STATUS = {404, 429, 500, 502, 503, 504}
# Errores de la solicitud o de la clave: cambiar de modelo no ayuda.
FATAL_STATUS = {400, 401, 403}

PER_CALL_TIMEOUT = 30   # segundos por intento
TOTAL_BUDGET = 58       # segundos para toda la respuesta
MAX_DISCOVERED = 3      # modelos extra descubiertos automáticamente
EXCLUDE = ("tts", "image", "live", "audio", "embed", "robotics", "aqa")


class GeminiError(Exception):
    pass


class GeminiClient:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.models = [m.strip() for m in model.split(",") if m.strip()]
        self.last_model = None

    # ------------------------------------------------------------------
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
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1500},
        }
        deadline = time.monotonic() + TOTAL_BUDGET
        tried, errors = [], []

        def attempt(model):
            tried.append(model)
            text, err = self._call(model, body, deadline)
            if text is not None:
                self.last_model = model
                return text
            errors.append(f"{model}: {err}")
            return None

        for model in self.models:
            out = attempt(model)
            if out is not None:
                return out

        # Se agotó la lista: descubrir otros modelos flash disponibles.
        if time.monotonic() < deadline:
            for model in self._discover(exclude=tried)[:MAX_DISCOVERED]:
                out = attempt(model)
                if out is not None:
                    return out

        raise GeminiError(
            "Ningún modelo de Gemini respondió (probados: "
            + ", ".join(tried) + "). Último error: " + (errors[-1] if errors else "?")
        )

    # ------------------------------------------------------------------
    def _call(self, model, body, deadline):
        """Un intento. Devuelve (texto, None) o (None, motivo). Lanza GeminiError
        solo ante errores fatales (clave inválida, solicitud mal formada)."""
        remaining = deadline - time.monotonic()
        if remaining < 3:
            return None, "sin tiempo restante"
        try:
            r = requests.post(
                ENDPOINT.format(model=model),
                headers={"x-goog-api-key": self.api_key},
                json=body,
                timeout=min(PER_CALL_TIMEOUT, remaining),
            )
        except requests.RequestException as e:
            return None, f"error de red ({type(e).__name__})"
        if r.status_code in FATAL_STATUS:
            raise GeminiError(f"Gemini rechazó la solicitud ({r.status_code}): {r.text[:200]}")
        if r.status_code in SWITCH_STATUS:
            return None, f"HTTP {r.status_code}"
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        try:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip(), None
        except (KeyError, IndexError, ValueError):
            return None, "respuesta vacía (posible bloqueo de seguridad)"

    def _discover(self, exclude):
        """Lista modelos 'flash' con generateContent, los más nuevos primero."""
        try:
            r = requests.get(f"{BASE}/models", params={"pageSize": 100},
                             headers={"x-goog-api-key": self.api_key}, timeout=8)
            if r.status_code != 200:
                return []
            names = []
            for m in r.json().get("models", []):
                name = m.get("name", "").removeprefix("models/")
                if ("flash" in name
                        and "generateContent" in m.get("supportedGenerationMethods", [])
                        and not any(x in name for x in EXCLUDE)
                        and name not in exclude):
                    names.append(name)
            return sorted(names, reverse=True)
        except (requests.RequestException, ValueError):
            return []
