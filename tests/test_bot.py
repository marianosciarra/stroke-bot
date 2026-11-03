import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot import nihss  # noqa: E402
from bot.config import Config  # noqa: E402
from bot.handlers import process_update  # noqa: E402
from bot.prompts import DISCLAIMER  # noqa: E402

UID, CHAT = 111, 111


class FakeTG:
    def __init__(self):
        self.sent, self.edits, self.downloads = [], [], []

    def send_message(self, chat_id, text, reply_markup=None, reply_to=None):
        self.sent.append((text, reply_markup))

    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        self.edits.append((text, reply_markup))

    def answer_callback(self, *a, **k): pass
    def send_action(self, *a, **k): pass

    def download_file(self, file_id):
        self.downloads.append(file_id)
        return b"img-" + file_id.encode(), "image/jpeg"


class FakeLLM:
    def __init__(self):
        self.calls = []

    def generate(self, prompt, images=()):
        self.calls.append((prompt, list(images)))
        return "RESULTADO SIMULADO"


def cfg(allowed=(UID,)):
    return Config(allowed_user_ids=set(allowed))


def cb(data):
    return {"callback_query": {"id": "1", "from": {"id": UID}, "data": data,
            "message": {"message_id": 5, "chat": {"id": CHAT}}}}


def msg(text=None, **extra):
    m = {"from": {"id": UID}, "chat": {"id": CHAT}}
    if text:
        m["text"] = text
    m.update(extra)
    return {"message": m}


# ---------------------------------------------------------------- NIHSS
def test_nihss_has_15_scored_items_and_max_42():
    assert nihss.N_ITEMS == 15
    assert sum(max(s for s, _ in opts) for _, opts in nihss.ITEMS) == 42


def test_severity_bands():
    assert nihss.severity(0).startswith("Sin")
    assert "menor" in nihss.severity(4)
    assert "moderado (5" in nihss.severity(5)
    assert "moderado a grave" in nihss.severity(16)
    assert "grave (21" in nihss.severity(21)


def test_nihss_full_flow_and_back():
    tg, llm = FakeTG(), FakeLLM()
    process_update(cb("m:nihss"), tg, llm, cfg())
    answers = ""
    # responde 1 a cada ítem, con un "Atrás" intercalado
    for i in range(nihss.N_ITEMS):
        if i == 3:
            process_update(cb(f"nb:{answers}"), tg, llm, cfg())  # vuelve al ítem 3
            assert tg.edits[-1][0].startswith("NIHSS (3/15)")
            answers = answers[:-1]
            process_update(cb(f"n:{answers}:1"), tg, llm, cfg())
            answers += "1"
        process_update(cb(f"n:{answers}:1"), tg, llm, cfg())
        answers += "1"
    final = tg.edits[-1][0]
    assert "PUNTAJE TOTAL: 15/42" in final
    assert "ACV moderado" in final
    assert DISCLAIMER in final


def test_callback_data_within_telegram_limit():
    _, kb = nihss.question("1" * 14)
    for row in kb["inline_keyboard"]:
        for b in row:
            assert len(b["callback_data"].encode()) <= 64


# ---------------------------------------------------------------- Auth
def test_unauthorized_user_blocked():
    tg, llm = FakeTG(), FakeLLM()
    process_update(msg("/stroke"), tg, llm, cfg(allowed=()))
    assert "No autorizado" in tg.sent[0][0] and "111" in tg.sent[0][0]
    process_update(cb("m:nihss"), tg, llm, cfg(allowed=()))
    assert not tg.edits and not llm.calls


# ---------------------------------------------------------------- Imágenes
def test_menu_opens():
    tg = FakeTG()
    process_update(msg("/stroke"), tg, FakeLLM(), cfg())
    assert len(tg.sent[0][1]["inline_keyboard"]) == 4


def test_mismatch_two_step_flow():
    tg, llm = FakeTG(), FakeLLM()
    process_update(cb("m:mismatch"), tg, llm, cfg())
    ask_dwi = tg.sent[-1][0]
    assert "[[mm1]]" in ask_dwi

    process_update(msg(photo=[{"file_id": "small"}, {"file_id": "DWI_ID-1"}],
                       reply_to_message={"text": ask_dwi}), tg, llm, cfg())
    ask_flair = tg.sent[-1][0]
    assert "[[mm2:DWI_ID-1]]" in ask_flair and not llm.calls

    process_update(msg(document={"file_id": "FLAIR_ID", "mime_type": "image/png"},
                       reply_to_message={"text": ask_flair}), tg, llm, cfg())
    assert tg.downloads == ["DWI_ID-1", "FLAIR_ID"]
    prompt, imgs = llm.calls[0]
    assert len(imgs) == 2 and "DWI" in prompt
    out = tg.sent[-1][0]
    assert "RESULTADO SIMULADO" in out and DISCLAIMER in out


def test_territory_and_volume_single_image_with_note():
    for data, marker in (("m:terr", "[[terr]]"), ("m:vol", "[[vol]]")):
        tg, llm = FakeTG(), FakeLLM()
        process_update(cb(data), tg, llm, cfg())
        ask = tg.sent[-1][0]
        assert marker in ask
        process_update(msg(photo=[{"file_id": "IMG"}], caption="espesor 5 mm, 6 cortes",
                           reply_to_message={"text": ask}), tg, llm, cfg())
        prompt, imgs = llm.calls[0]
        assert len(imgs) == 1 and "espesor 5 mm" in prompt
        assert DISCLAIMER in tg.sent[-1][0]


def test_image_without_context_is_rejected():
    tg, llm = FakeTG(), FakeLLM()
    process_update(msg(photo=[{"file_id": "X"}]), tg, llm, cfg())
    assert not llm.calls and "módulo" in tg.sent[0][0]


def test_llm_error_reported_not_raised():
    from bot.gemini_client import GeminiError

    class Boom(FakeLLM):
        def generate(self, *a, **k):
            raise GeminiError("límite")

    tg = FakeTG()
    process_update(cb("m:terr"), tg, Boom(), cfg())
    ask = tg.sent[-1][0]
    process_update(msg(photo=[{"file_id": "I"}], reply_to_message={"text": ask}),
                   tg, Boom(), cfg())
    assert "No pude analizar" in tg.sent[-1][0]
