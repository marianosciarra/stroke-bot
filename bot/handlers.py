"""Lógica del bot, sin estado en servidor.

Estado:
- NIHSS: dígitos acumulados dentro del callback_data de los botones.
- Imágenes: el bot pide la foto "respondiendo a este mensaje"; el mensaje del
  bot lleva un marcador [[...]] que identifica el módulo (y, en el mismatch,
  el file_id de la DWI ya recibida).
"""
import re

from . import nihss
from .gemini_client import GeminiError
from .prompts import DISCLAIMER, MISMATCH, TERRITORIO, VOLUMEN

MARKER = re.compile(r"\[\[(mm1|mm2|terr|vol)(?::([A-Za-z0-9_-]+))?\]\]")

MENU_TEXT = "Soporte ACV - elegí un módulo:"
MENU = {"inline_keyboard": [
    [{"text": "Calculadora NIHSS", "callback_data": "m:nihss"}],
    [{"text": "Mismatch DWI / FLAIR", "callback_data": "m:mismatch"}],
    [{"text": "Territorio vascular (arterial / venoso)", "callback_data": "m:terr"}],
    [{"text": "Volumen de isquemia (ABC/2)", "callback_data": "m:vol"}],
]}

ANON = ("Antes de enviar imágenes: anonimizalas (sin nombre, DNI ni fecha de "
        "nacimiento). Se procesan con la API de Gemini. Enviá la imagen como "
        "ARCHIVO (no como foto) para no perder calidad.")


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
    elif data == "m:mismatch":
        tg.send_message(chat_id, "Mismatch DWI/FLAIR.\n" + ANON +
                        "\n\nRespondé a ESTE mensaje con la imagen DWI.\n[[mm1]]")
    elif data == "m:terr":
        tg.send_message(chat_id, "Territorio vascular.\n" + ANON +
                        "\n\nRespondé a ESTE mensaje con la imagen (podés agregar "
                        "un texto con datos, por ejemplo secuencia o clínica).\n[[terr]]")
    elif data == "m:vol":
        tg.send_message(chat_id, "Volumen de isquemia (ABC/2).\n" + ANON +
                        "\n\nRespondé a ESTE mensaje con la imagen. En el texto "
                        "indicá espesor de corte y cantidad de cortes con lesión "
                        "(ej: 'espesor 5 mm, 6 cortes').\n[[vol]]")


# ----------------------------------------------------------------- mensajes
def _on_message(msg, tg, llm, cfg):
    user_id = msg["from"]["id"]
    chat_id = msg["chat"]["id"]
    if not _authorized(user_id, cfg):
        _deny(tg, chat_id, user_id)
        return

    text = (msg.get("text") or "").strip()
    if text.startswith(("/start", "/stroke", "/menu")):
        tg.send_message(chat_id, MENU_TEXT, MENU)
        return
    if text.startswith("/nihss"):
        t, kb = nihss.question("")
        tg.send_message(chat_id, t, kb)
        return

    file_id = _image_file_id(msg)
    if file_id:
        _on_image(msg, file_id, tg, llm)
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
        tg.send_message(chat_id, "Elegí primero un módulo con /stroke y respondé "
                                 "al mensaje del bot con la imagen.")
        return
    kind, extra = m.group(1), m.group(2)
    note = (msg.get("caption") or "").strip()

    if kind == "mm1":  # llegó la DWI, pedir la FLAIR
        tg.send_message(
            chat_id,
            "DWI recibida. Ahora respondé a ESTE mensaje con la imagen FLAIR "
            "(mismo nivel de corte, si es posible).\n"
            f"(No borres esta línea)\n[[mm2:{file_id}]]",
        )
        return

    try:
        tg.send_action(chat_id)
        if kind == "mm2":
            dwi = tg.download_file(extra)
            flair = tg.download_file(file_id)
            prompt, imgs = MISMATCH, [dwi, flair]
            title = "Evaluación de mismatch DWI / FLAIR"
        else:
            img = tg.download_file(file_id)
            prompt, imgs = (TERRITORIO if kind == "terr" else VOLUMEN), [img]
            title = ("Territorio vascular" if kind == "terr"
                     else "Estimación de volumen de isquemia")
        if note:
            prompt += f"\nDatos aportados por el usuario: {note}\n"
        result = llm.generate(prompt, imgs)
    except GeminiError as e:
        tg.send_message(chat_id, f"No pude analizar la imagen: {e}")
        return
    except Exception as e:  # descarga de Telegram, red, etc.
        tg.send_message(chat_id, f"Error procesando la imagen: {e}")
        return

    tg.send_message(chat_id, f"{title}\n\n{result}\n\n{DISCLAIMER}",
                    reply_markup={"inline_keyboard": [
                        [{"text": "Menú", "callback_data": "m:menu"}]]})
