"""
Motor de búsqueda de temas: 100% gratis, sin API externa.
Usa rapidfuzz (fuzzy matching) sobre título + palabras clave de cada tema.
Si el usuario escribe con errores, sinónimos o de forma incompleta,
igual encuentra el tema más parecido.
"""
import json
from rapidfuzz import fuzz, process

with open("content.json", encoding="utf-8") as f:
    DATA = json.load(f)

TOPICS = {t["id"]: t for t in DATA["topics"]}

# Índice: para cada tema, todas las frases que pueden llevar a él
_CHOICES = {}
for t in DATA["topics"]:
    frases = [t["titulo"]] + t.get("keywords", [])
    for frase in frases:
        _CHOICES[frase.lower()] = t["id"]


def buscar_tema(consulta: str, umbral: int = 60):
    """
    Devuelve (topic, score) del tema más parecido a la consulta,
    o (None, 0) si nada supera el umbral mínimo de similitud.
    """
    if not consulta or not consulta.strip():
        return None, 0

    consulta = consulta.lower().strip()

    match = process.extractOne(
        consulta, _CHOICES.keys(), scorer=fuzz.token_set_ratio
    )
    if match is None:
        return None, 0

    frase, score, _ = match
    if score < umbral:
        return None, 0

    topic_id = _CHOICES[frase]
    return TOPICS[topic_id], score


def sugerencias(consulta: str, n: int = 3, umbral: int = 45):
    """Devuelve hasta n temas parecidos, útil cuando no hay match claro."""
    if not consulta or not consulta.strip():
        return []
    consulta = consulta.lower().strip()
    matches = process.extract(
        consulta, _CHOICES.keys(), scorer=fuzz.token_set_ratio, limit=10
    )
    vistos = set()
    resultado = []
    for frase, score, _ in matches:
        if score < umbral:
            continue
        topic_id = _CHOICES[frase]
        if topic_id in vistos:
            continue
        vistos.add(topic_id)
        resultado.append(TOPICS[topic_id])
        if len(resultado) >= n:
            break
    return resultado


def tema_por_id(topic_id: str):
    return TOPICS.get(topic_id)


def todos_los_temas():
    return DATA["topics"]