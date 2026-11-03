"""Escala NIHSS: 11 ítems (15 puntajes). El estado viaja en el callback_data
como cadena de dígitos (una por ítem respondido), así no hace falta memoria."""

ITEMS = [
    ("1a. Nivel de conciencia", [
        (0, "Alerta"),
        (1, "Somnoliento, despierta con estímulo menor"),
        (2, "Requiere estímulo repetido o doloroso"),
        (3, "Sólo respuestas reflejas / sin respuesta"),
    ]),
    ("1b. Preguntas de orientación (mes y edad)", [
        (0, "Ambas correctas"),
        (1, "Una correcta"),
        (2, "Ninguna correcta"),
    ]),
    ("1c. Órdenes (abrir/cerrar ojos, apretar/soltar mano)", [
        (0, "Realiza ambas"),
        (1, "Realiza una"),
        (2, "Ninguna"),
    ]),
    ("2. Mirada conjugada", [
        (0, "Normal"),
        (1, "Paresia parcial de la mirada"),
        (2, "Desviación forzada / paresia total"),
    ]),
    ("3. Campo visual", [
        (0, "Sin pérdida"),
        (1, "Hemianopsia parcial (cuadrantanopsia)"),
        (2, "Hemianopsia completa"),
        (3, "Hemianopsia bilateral / ceguera"),
    ]),
    ("4. Parálisis facial", [
        (0, "Normal"),
        (1, "Leve (asimetría al sonreír)"),
        (2, "Parcial (parálisis facial inferior total o casi)"),
        (3, "Completa (superior e inferior)"),
    ]),
    ("5a. Motor brazo izquierdo", [
        (0, "Sin claudicación (10 s)"),
        (1, "Claudica antes de 10 s, sin tocar la cama"),
        (2, "Cierto esfuerzo contra gravedad"),
        (3, "Sin esfuerzo contra gravedad"),
        (4, "Sin movimiento"),
    ]),
    ("5b. Motor brazo derecho", [
        (0, "Sin claudicación (10 s)"),
        (1, "Claudica antes de 10 s, sin tocar la cama"),
        (2, "Cierto esfuerzo contra gravedad"),
        (3, "Sin esfuerzo contra gravedad"),
        (4, "Sin movimiento"),
    ]),
    ("6a. Motor pierna izquierda", [
        (0, "Sin claudicación (5 s)"),
        (1, "Claudica antes de 5 s, sin tocar la cama"),
        (2, "Cierto esfuerzo contra gravedad"),
        (3, "Sin esfuerzo contra gravedad"),
        (4, "Sin movimiento"),
    ]),
    ("6b. Motor pierna derecha", [
        (0, "Sin claudicación (5 s)"),
        (1, "Claudica antes de 5 s, sin tocar la cama"),
        (2, "Cierto esfuerzo contra gravedad"),
        (3, "Sin esfuerzo contra gravedad"),
        (4, "Sin movimiento"),
    ]),
    ("7. Ataxia de miembros", [
        (0, "Ausente"),
        (1, "Presente en un miembro"),
        (2, "Presente en dos miembros"),
    ]),
    ("8. Sensibilidad", [
        (0, "Normal"),
        (1, "Pérdida leve a moderada"),
        (2, "Pérdida severa o total"),
    ]),
    ("9. Lenguaje", [
        (0, "Sin afasia"),
        (1, "Afasia leve a moderada"),
        (2, "Afasia severa"),
        (3, "Mutismo / afasia global"),
    ]),
    ("10. Disartria", [
        (0, "Normal"),
        (1, "Leve a moderada"),
        (2, "Severa / anartria"),
    ]),
    ("11. Extinción / inatención", [
        (0, "Sin anormalidad"),
        (1, "Inatención en una modalidad"),
        (2, "Hemi-inatención profunda o en más de una modalidad"),
    ]),
]

N_ITEMS = len(ITEMS)  # 15 puntajes (11 ítems con subítems)


def total(answers: str) -> int:
    return sum(int(c) for c in answers)


def severity(score: int) -> str:
    if score == 0:
        return "Sin síntomas de ACV"
    if score <= 4:
        return "ACV menor (1-4)"
    if score <= 15:
        return "ACV moderado (5-15)"
    if score <= 20:
        return "ACV moderado a grave (16-20)"
    return "ACV grave (21-42)"


def question(answers: str):
    """Texto + teclado para el próximo ítem, o None si terminó."""
    idx = len(answers)
    if idx >= N_ITEMS:
        return None
    title, options = ITEMS[idx]
    text = f"NIHSS ({idx + 1}/{N_ITEMS}) - Parcial: {total(answers)}\n\n{title}"
    rows = [[{"text": f"{s} - {label}", "callback_data": f"n:{answers}:{s}"}]
            for s, label in options]
    nav = []
    if idx > 0:
        nav.append({"text": "Atrás", "callback_data": f"nb:{answers}"})
    nav.append({"text": "Cancelar", "callback_data": "m:menu"})
    rows.append(nav)
    return text, {"inline_keyboard": rows}


def summary(answers: str) -> str:
    lines = ["Resultado NIHSS", ""]
    for (title, options), c in zip(ITEMS, answers):
        label = dict(options)[int(c)]
        lines.append(f"{title}: {c} ({label})")
    t = total(answers)
    lines += ["", f"PUNTAJE TOTAL: {t}/42", f"Categoría: {severity(t)}"]
    return "\n".join(lines)
