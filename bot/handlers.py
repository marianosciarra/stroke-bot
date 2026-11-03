"""Lógica del bot, sin estado en servidor.

Estado:
- NIHSS: dígitos acumulados dentro del callback_data de los botones.
- Imágenes: el bot pide la imagen "respondiendo a su mensaje"; ese mensaje
  lleva un marcador [[...]] que identifica el módulo (y, en el mismatch,
  el file_id de la DWI ya recibida).
"""
import re

from . import nihss
from .gemini_client import GeminiError
from .prompts import DISCLAIMER, HEMATOMA, MISMATCH, TERRITORIO, VOLUMEN

MARKER = re.compile(r"\[\[(mm1|mm2|terr|vol|hem)(?::([A-Za-z0-9_-]+))?\]\]")
FORCE_REPLY = {"force_reply": True}

MENU_TEXT = "Soporte ACV - elegí un módulo:"
MENU = {"inline_keyboard": [
    [{"text": "Calculadora NIHSS", "callback_data": "m:nihss"}],
    [{"text": "Mismatch DWI / FLAIR", "callback_data": "m:mismatch"}],
    [{"text": "Territorio vascular", "callback_data": "m:terr"}],
    [{"text": "Volumen de isquemia", "callback_data": "m:vol"}],
    [{"text": "Hematoma / tumor (volumen)", "callback_data": "m:hem"}],
]}

NO_PHI = "Sin datos del paciente en la imagen."
CLICK = "Hacé clic sobre ESTE mensaje para responder"

ASK = {
    "mm1": (f"MISMATCH DWI/FLAIR\n{CLICK} con la imagen DWI.\n{NO_PHI}\n[[mm1]]"),
    "terr": (f"TERRITORIO VASCULAR\n{CLICK} con la imagen.\n{NO_PHI}\n[[terr]]"),
    "vol": (
        "VOLUMEN DE ISQUEMIA (ABC/2)\n"
        f"{CLICK}.\n"
        "Rápido, sin imagen: escribí las medidas en cm.\n"
        "Ej: A 4.2 B 3 cortes 6 espesor 5mm\n"
        "(A = diámetro mayor, B = perpendicular, cortes = los que tienen lesión)\n"
        "Con imagen: el corte de mayor lesión, con la escala visible.\n"
        f"{NO_PHI}\n[[vol]]"
    ),
    "hem": (
        "HEMATOMA / TUMOR (ABC/2)\n"
        f"{CLICK}.\n"
        "Rápido, sin imagen: escribí las medidas en cm.\n"
        "Ej: A 4.2 B 3 cortes 6 espesor 5mm\n"
        "Hematoma: contá cortes con >=75% del área máx. = 1 y con 25-75% = 0,5.\n"
        "Con imagen: el corte de mayor lesión, con la escala visible. "
        "Aclará si es hematoma o tumor.\n"
        f"{NO_PHI}\n[[hem]]"
    ),
}
ASK_BY_CALLBACK = {"m:mismatch": "mm1", "m:terr": "terr", "m:vol": "vol", "m:hem": "hem"}
TITLES = {
    "mm2": "MISMATCH DWI / FLAIR",
    "terr": "TERRITORIO VASCULAR",
    "vol": "VOLUMEN DE ISQUEMIA",
    "hem": "HEMATOMA / TUMOR",
}


# ------------------------------------------------------- cálculo de volumen
_NUM = r"(\d+(?:[.,]\d+)?)"


def _f(s: str) -> float:
    return float(s.replace(",", "."))


def parse_measures(text: str):
    """Devuelve (A, B, C) en cm; None en lo que falte.
    Acepta 'A 4.2 B 3 C 2.5' o 'A 4.2 B 3 cortes 6 espesor 5mm'."""
    t = (text or "").lower()

    def grab(letter):
        m = re.search(rf"\b{letter}\s*[:=]?\s*{_NUM}\s*(mm|cm)?", t)
        if not m:
            return None
        v = _f(m.group(1))
        return v / 10 if m.group(2) == "mm" else v

    a, b, c = grab("a"), grab("b"), grab("c")
    if c is None:
        # "cortes 6" tiene prioridad; "6 cortes" solo si no hay otra forma
        n = (re.search(r"cortes\s*[:=]?\s*(\d+(?:[.,]\d+)?)", t)
             or re.search(r"(\d+(?:[.,]\d+)?)\s*cortes", t))
        e = re.search(rf"(?:espesor|esp\.?)\s*[:=]?\s*{_NUM}", t)
        if n and e:
            c = _f(n.group(1)) * _f(e.group(1)) / 10
    return a, b, c


def format_volume(a, b, c, kind="vol") -> str:
    v = a * b * c / 2
    lines = [f"VOLUMEN: {v:.1f} mL", f"A {a:g} x B {b:g} x C {c:.2g} cm / 2"]
    if kind == "hem" and v >= 30:
        lines.append("Hematoma >=30 mL: suma 1 punto en el ICH score.")
    lines.append("ABC/2 sobreestima lesiones irregulares.")
    return "\n".join(lines)


def _missing_text(a, b, c):
    falta = [n for n, x in (("A", a), ("B", b), ("C (o cortes y espesor)", c)) if x is None]
    return ("Faltan medidas: " + ", ".join(falta) +
            ".\nEj: A 4.2 B 3 cortes 6 espesor 5mm")


def process_update(update: dict, tg, llm, cfg) -> None:
    if "callback_query" in update:
        _on_callback(update["callback_query"], tg, llm, cfg)
    elif "message" in update:
        _on_message(update["message"], tg, llm, cfg)


def _authorized(user_id, cfg) -> bool:
    return user_id in cfg.allowed_user_ids


def _deny(tg, chat_id, user_id):
    tg.send_message(chat_id, f"No autorizado. Tu ID de Telegram es {user_id}.")


# ---------------------------------------------------------------- callbacks
def _on_callback(cq, tg, llm, cfg):
    user_id = cq["from"]["id"]
    chat_id = cq["message"]["chat"]["id"]
    msg_id = cq["message"]["message_id"]
    data = cq.get("data", "")
    if not _authorized(user_id, cfg):
        tg.answer_callback(cq["id"], "No autorizado")
        return
    tg.answer_callback(cq["id"])

    if data == "m:menu":
        tg.edit_message(chat_id, msg_id, MENU_TEXT, MENU)
    elif data == "m:nihss":
        text, kb = nihss.question("")
        tg.edit_message(chat_id, msg_id, text, kb)
    elif data.startswith("nb:"):
        answers = data[3:][:-1]
        text, kb = nihss.question(answers)
        tg.edit_message(chat_id, msg_id, text, kb)
    elif data.startswith("n:"):
        _, answers, score = data.split(":")
        answers += score
        nxt = nihss.question(answers)
        if nxt:
            tg.edit_message(chat_id, msg_id, *nxt)
        else:
            kb = {"inline_keyboard": [
                [{"text": "Repetir", "callback_data": "m:nihss"}],
                [{"text": "Menú", "callback_data": "m:menu"}],
            ]}
            tg.edit_message(chat_id, msg_id,
                            nihss.summary(answers) + "\n\n" + DISCLAIMER, kb)
    elif data in ASK_BY_CALLBACK:
        tg.send_message(chat_id, ASK[ASK_BY_CALLBACK[data]], reply_markup=FORCE_REPLY)


# ----------------------------------------------------------------- mensajes
def _on_message(msg, tg, llm, cfg):
    user_id = msg["from"]["id"]
    chat_id = msg["chat"]["id"]
    if not _authorized(user_id, cfg):
        _deny(tg, chat_id, user_id)
        return

    text = (msg.get("text") or "").strip()
    low = text.lower()
    if low.startswith(("/start", "/stroke", "/menu")):
        tg.send_message(chat_id, MENU_TEXT, MENU)
        return
    if low.startswith("/nihss"):
        t, kb = nihss.question("")
        tg.send_message(chat_id, t, kb)
        return
    if low.startswith("/hematoma"):
        tg.send_message(chat_id, ASK["hem"], reply_markup=FORCE_REPLY)
        return
    if low.startswith("/abc"):
        nums = re.findall(_NUM, text[4:])
        if len(nums) == 3:
            a, b, c = (_f(x) for x in nums)
        else:
            a, b, c = parse_measures(text[4:])
        if None in (a, b, c):
            tg.send_message(chat_id, "Uso: /abc A B C (en cm)\nEj: /abc 4.2 3 2.5")
        else:
            tg.send_message(chat_id, format_volume(a, b, c) + "\n\n" + DISCLAIMER)
        return

    file_id = _image_file_id(msg)
    if file_id:
        _on_image(msg, file_id, tg, llm)
        return

    # Texto como respuesta a un módulo de volumen: calcular directo.
    reply_text = (msg.get("reply_to_message") or {}).get("text") or ""
    m = MARKER.search(reply_text)
    if m and m.group(1) in ("vol", "hem") and text:
        kind = m.group(1)
        a, b, c = parse_measures(text)
        if None in (a, b, c):
            tg.send_message(chat_id, _missing_text(a, b, c), reply_markup=FORCE_REPLY)
        else:
            tg.send_message(chat_id, format_volume(a, b, c, kind) + "\n\n" + DISCLAIMER,
                            reply_markup={"inline_keyboard": [
                                [{"text": "Menú", "callback_data": "m:menu"}]]})
        return

    tg.send_message(chat_id, "Usá /stroke para abrir el menú.")


def _image_file_id(msg):
    if msg.get("photo"):
        return msg["photo"][-1]["file_id"]  # mayor resolución
    doc = msg.get("document")
    if doc and str(doc.get("mime_type", "")).startswith("image/"):
        return doc["file_id"]
    return None


def _on_image(msg, file_id, tg, llm):
    chat_id = msg["chat"]["id"]
    reply = msg.get("reply_to_message") or {}
    m = MARKER.search(reply.get("text") or "")
    if not m:
        tg.send_message(chat_id, "Elegí un módulo con /stroke y respondé a su "
                                 "mensaje con la imagen.")
        return
    kind, extra = m.group(1), m.group(2)
    note = (msg.get("caption") or "").strip()
    done_kb = {"inline_keyboard": [[{"text": "Menú", "callback_data": "m:menu"}]]}

    if kind == "mm1":  # llegó la DWI, pedir la FLAIR
        tg.send_message(
            chat_id,
            f"DWI recibida. {CLICK} con la imagen FLAIR (mismo corte).\n[[mm2:{file_id}]]",
            reply_markup=FORCE_REPLY,
        )
        return

    # Volumen: si trae medidas en el texto, se calcula al instante, sin imagen.
    if kind in ("vol", "hem") and note:
        a, b, c = parse_measures(note)
        if None not in (a, b, c):
            tg.send_message(chat_id, f"{TITLES[kind]}\n" + format_volume(a, b, c, kind)
                            + "\n\n" + DISCLAIMER, reply_markup=done_kb)
            return

    try:
        tg.send_action(chat_id)
        if kind == "mm2":
            imgs = [tg.download_file(extra), tg.download_file(file_id)]
            prompt = MISMATCH
        else:
            imgs = [tg.download_file(file_id)]
            prompt = {"terr": TERRITORIO, "vol": VOLUMEN, "hem": HEMATOMA}[kind]
        if note:
            prompt += f"\nDatos aportados por el usuario: {note}\n"
        result = llm.generate(prompt, imgs)
    except GeminiError as e:
        print(f"analisis fallido: {e}")
        tg.send_message(chat_id, "No se pudo analizar la imagen ahora (servicio "
                                 "ocupado). Reintentá en un momento.",
                        reply_markup=done_kb)
        return
    except Exception as e:  # descarga de Telegram, red, etc.
        print(f"error procesando imagen: {e!r}")
        tg.send_message(chat_id, "No se pudo procesar la imagen. Probá enviarla "
                                 "de nuevo, como archivo.", reply_markup=done_kb)
        return

    tg.send_message(chat_id, f"{TITLES[kind]}\n{result}\n\n{DISCLAIMER}",
                    reply_markup=done_kb)
