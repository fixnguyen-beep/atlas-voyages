import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog.json"
OUTPUT = ROOT / "data" / "trends.json"
API_URL = "https://api.openai.com/v1"
MODEL_RESEARCH = os.getenv("OPENAI_RESEARCH_MODEL", "gpt-4.1-mini")
MODEL_EXTRACT = os.getenv("OPENAI_EXTRACT_MODEL", "gpt-4o-mini")
BATCH_SIZE = int(os.getenv("ATLAS_BATCH_SIZE", "5"))
TIMEOUT = 180

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def api_post(path, payload):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY absent")
    response = requests.post(
        f"{API_URL}/{path}",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(f"OpenAI HTTP {response.status_code}: {response.text[:900]}")
    return response.json()


def response_text(result):
    chunks = []
    for item in result.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    chunks.append(part.get("text", ""))
    return "\n".join(chunks)


def valid_url(value):
    try:
        parsed = urlparse(value)
        return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username and not parsed.password
    except (TypeError, ValueError):
        return False


def research_batch(batch):
    compact = [
        {
            "destination": item["destination"],
            "preferences": item.get("preferences", {}),
            "editorial_stays": [entry.split("|")[0] for entry in item.get("editorial_stays", [])],
        }
        for item in batch
    ]
    prompt = f"""
Date UTC : {datetime.now(timezone.utc).date()}.
Effectue une recherche web sourcée pour l'Atlas de voyage ci-dessous.
Destinations et critères : {json.dumps(compact, ensure_ascii=False)}

Pour chaque destination, recherche uniquement des informations vérifiables :
1. jusqu'à 3 hôtels actuellement ouverts correspondant aux critères ;
2. jusqu'à 3 conseils récents utiles au voyageur (accès, saison, restrictions, ouverture importante) ;
3. les ouvertures d'hôtels de luxe publiées ou annoncées avec une date précise.

Priorité aux sites officiels des hôtels, offices de tourisme, compagnies aériennes et médias professionnels reconnus.
Ne déduis pas qu'un hôtel est ouvert sans source. N'invente ni prix, ni classement, ni date.
Pour chaque fait, donne l'URL HTTPS complète, l'éditeur et la date de publication si elle est disponible.
Ignore les informations impossibles à corroborer. Réponds en français.
""".strip()
    result = api_post("responses", {
        "model": MODEL_RESEARCH,
        "tools": [{"type": "web_search_preview"}],
        "tool_choice": "required",
        "input": prompt,
        "max_output_tokens": 5000,
    })
    text = response_text(result)
    if not text.strip():
        raise RuntimeError("Recherche web sans texte de réponse")
    return text


def extract_batch(research_text, allowed):
    instructions = f"""
Transforme le texte de recherche en JSON strict, sans ajouter la moindre information.
Destinations permises : {json.dumps(sorted(allowed), ensure_ascii=False)}.
Retourne exactement un objet avec trois tableaux : destinations, signals, hotel_openings.

Chaque entrée destinations contient :
- destination
- hotels : tableau de 0 à 3 objets avec name, location, description, official_url, source_url, source_publisher, published_at
- advice : tableau de 0 à 3 objets avec title, detail, source_url, source_publisher, published_at

Chaque entrée signals contient : destination, title, detail, publisher, url, published_at.
Chaque entrée hotel_openings contient : hotel_name, country, city, opened_in, official_url, source_url, source_publisher, summary.

Règles :
- URL obligatoirement présente dans le texte source et en HTTPS ;
- published_at et opened_in au format YYYY-MM-DD ou null ;
- ne pas inventer de rang, prix, score ou date ;
- si une information n'est pas étayée, l'omettre ;
- maximum 12 signals et 10 hotel_openings.
""".strip()
    result = api_post("chat/completions", {
        "model": MODEL_EXTRACT,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": research_text},
        ],
    })
    return json.loads(result["choices"][0]["message"]["content"])


def clean_date(value):
    return value if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else None


def clean_dynamic(raw, allowed):
    by_destination = {}
    for record in raw.get("destinations", []):
        destination = record.get("destination")
        if destination not in allowed:
            continue
        hotels = []
        for hotel in record.get("hotels", [])[:3]:
            if not all(isinstance(hotel.get(k), str) and hotel[k].strip() for k in ("name", "location", "description", "official_url", "source_url", "source_publisher")):
                continue
            if not valid_url(hotel["official_url"]) or not valid_url(hotel["source_url"]):
                continue
            hotels.append({
                "name": hotel["name"].strip(), "location": hotel["location"].strip(),
                "description": hotel["description"].strip(), "official_url": hotel["official_url"],
                "source_url": hotel["source_url"], "source_publisher": hotel["source_publisher"].strip(),
                "published_at": clean_date(hotel.get("published_at")), "status": "web_researched",
            })
        advice = []
        for tip in record.get("advice", [])[:3]:
            if not all(isinstance(tip.get(k), str) and tip[k].strip() for k in ("title", "detail", "source_url", "source_publisher")):
                continue
            if not valid_url(tip["source_url"]):
                continue
            advice.append({
                "title": tip["title"].strip(), "detail": tip["detail"].strip(),
                "source_url": tip["source_url"], "source_publisher": tip["source_publisher"].strip(),
                "published_at": clean_date(tip.get("published_at")),
            })
        by_destination[destination] = {"recommended_hotels": hotels, "current_advice": advice}

    signals = []
    seen = set()
    for signal in raw.get("signals", [])[:12]:
        if signal.get("destination") not in allowed or not valid_url(signal.get("url")):
            continue
        if not all(isinstance(signal.get(k), str) and signal[k].strip() for k in ("title", "detail", "publisher")):
            continue
        key = (signal["destination"], signal["url"])
        if key in seen:
            continue
        seen.add(key)
        signals.append({
            "destination": signal["destination"], "title": signal["title"].strip(),
            "detail": signal["detail"].strip(), "publisher": signal["publisher"].strip(),
            "url": signal["url"], "published_at": clean_date(signal.get("published_at")),
        })

    openings = []
    seen_openings = set()
    for opening in raw.get("hotel_openings", [])[:10]:
        required = ("hotel_name", "country", "city", "official_url", "source_url", "source_publisher", "summary")
        if not all(isinstance(opening.get(k), str) and opening[k].strip() for k in required):
            continue
        if not valid_url(opening["official_url"]) or not valid_url(opening["source_url"]):
            continue
        key = (opening["hotel_name"].casefold(), opening["country"].casefold())
        if key in seen_openings:
            continue
        seen_openings.add(key)
        openings.append({
            "hotel_name": opening["hotel_name"].strip(), "country": opening["country"].strip(),
            "city": opening["city"].strip(), "opened_in": clean_date(opening.get("opened_in")),
            "official_url": opening["official_url"], "source_url": opening["source_url"],
            "source_publisher": opening["source_publisher"].strip(), "summary": opening["summary"].strip(),
        })
    return by_destination, signals, openings


def editorial_hotels(item):
    hotels = []
    for entry in item.get("editorial_stays", []):
        parts = entry.split("|", 2)
        if len(parts) == 3:
            hotels.append({"name": parts[0], "location": parts[1], "description": parts[2], "status": "editorial"})
    return hotels


def main():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("data/catalog.json doit être une liste non vide")
    names = [item["destination"] for item in catalog]
    if len(names) != len(set(names)):
        raise ValueError("Destinations en double dans catalog.json")

    dynamic = {}
    signals = []
    openings = []
    allowed = set(names)
    for start in range(0, len(catalog), BATCH_SIZE):
        batch = catalog[start:start + BATCH_SIZE]
        logging.info("Recherche web : lot %d-%d", start + 1, start + len(batch))
        cleaned, batch_signals, batch_openings = clean_dynamic(extract_batch(research_batch(batch), allowed), allowed)
        dynamic.update(cleaned)
        signals.extend(batch_signals)
        openings.extend(batch_openings)

    old = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    old_by_name = {item.get("destination"): item for item in old.get("items", [])}
    items = []
    for item in catalog:
        name = item["destination"]
        fresh = dynamic.get(name, {})
        previous = old_by_name.get(name, {})
        recommended = fresh.get("recommended_hotels") or previous.get("recommended_hotels") or editorial_hotels(item)
        advice = fresh.get("current_advice") or previous.get("current_advice") or []
        items.append(item | {"recommended_hotels": recommended, "current_advice": advice})

    if not signals:
        signals = old.get("signals", [])
    if not openings:
        openings = old.get("hotel_openings", [])

    for rank, opening in enumerate(openings[:10], 1):
        opening["rank"] = rank

    payload = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": "Sélection éditoriale enrichie par une recherche web sourcée. Vérifier disponibilité et conditions avant réservation.",
        "items": sorted(items, key=lambda x: x.get("score", 0), reverse=True),
        "hotel_openings": openings[:10],
        "signals": signals[:30],
        "methodology": {
            "research_window_days": 45,
            "catalog_role": "editorial preferences and fallback content",
            "dynamic_role": "web-researched hotels, current advice and openings",
            "verification": "URLs required; availability and prices not verified",
        },
    }
    tmp = OUTPUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(OUTPUT)
    logging.info("data/trends.json mis à jour")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Échec de la mise à jour")
        sys.exit(1)
