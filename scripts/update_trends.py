import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog.json"
OUTPUT = ROOT / "data" / "trends.json"
API_URL = "https://api.openai.com/v1"
RESEARCH_MODEL = os.getenv("OPENAI_RESEARCH_MODEL", "gpt-4.1-mini")
EXTRACT_MODEL = os.getenv("OPENAI_EXTRACT_MODEL", "gpt-4o-mini")
TARGET_HOTELS = int(os.getenv("ATLAS_HOTELS_PER_PROFILE", "10"))
TARGET_OPENINGS = int(os.getenv("ATLAS_HOTEL_OPENINGS", "20"))
MAX_PASSES = int(os.getenv("ATLAS_MAX_PASSES", "3"))
TIMEOUT = 240

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def api_post(path, payload, attempts=3):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Le secret OPENAI_API_KEY est absent")

    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(
                f"{API_URL}/{path}",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=TIMEOUT,
            )
            if response.ok:
                return response.json()
            last_error = RuntimeError(
                f"OpenAI HTTP {response.status_code}: {response.text[:1200]}"
            )
            if response.status_code not in (408, 409, 429, 500, 502, 503, 504):
                raise last_error
        except requests.RequestException as exc:
            last_error = exc

        if attempt < attempts:
            time.sleep(3 * attempt)

    raise RuntimeError(f"Echec de l'appel OpenAI: {last_error}")


def response_text(result):
    chunks = []
    for item in result.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                chunks.append(part.get("text", ""))
    return "\n".join(chunks).strip()


def clean_url(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or not parsed.netloc:
            return None
        query = [
            (key, val)
            for key, val in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
        ]
        return urlunparse(parsed._replace(query=urlencode(query), fragment=""))
    except (TypeError, ValueError):
        return None


def clean_date(value):
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    return None


def normalise_name(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def same_destination(candidate_country, destination):
    if not candidate_country:
        return False
    return normalise_name(candidate_country) == normalise_name(destination)


def unique_hotels(hotels):
    result = []
    seen = set()
    for hotel in hotels:
        key = normalise_name(hotel.get("name"))
        if key and key not in seen:
            seen.add(key)
            result.append(hotel)
    return result


def clean_hotel(raw, destination, profile):
    required = (
        "name",
        "country",
        "location",
        "description",
        "official_url",
        "source_url",
        "source_publisher",
    )
    if not all(isinstance(raw.get(k), str) and raw[k].strip() for k in required):
        return None
    if not same_destination(raw.get("country"), destination):
        return None

    official_url = clean_url(raw.get("official_url"))
    source_url = clean_url(raw.get("source_url"))
    if not official_url or not source_url:
        return None

    return {
        "name": raw["name"].strip(),
        "country": destination,
        "location": raw["location"].strip(),
        "description": raw["description"].strip(),
        "official_url": official_url,
        "source_url": source_url,
        "source_publisher": raw["source_publisher"].strip(),
        "published_at": clean_date(raw.get("published_at")),
        "profile": profile,
        "status": "web_researched",
    }


def clean_advice(raw, destination, profile):
    required = ("title", "detail", "source_url", "source_publisher")
    if not all(isinstance(raw.get(k), str) and raw[k].strip() for k in required):
        return None
    source_url = clean_url(raw.get("source_url"))
    if not source_url:
        return None
    return {
        "destination": destination,
        "profile": profile,
        "title": raw["title"].strip(),
        "detail": raw["detail"].strip(),
        "source_url": source_url,
        "source_publisher": raw["source_publisher"].strip(),
        "published_at": clean_date(raw.get("published_at")),
    }


def research_destination_profile(item, profile, existing_names, missing):
    destination = item["destination"]
    profile_data = item.get("profiles", {}).get(profile, {})
    angle = profile_data.get("angle", "")
    excluded = ", ".join(existing_names) if existing_names else "aucun"

    prompt = f"""
Date UTC : {datetime.now(timezone.utc).date()}.
Effectue une recherche web exclusivement sur la destination suivante : {destination}.
Profil du voyage : {profile}.
Critères : {angle}

Trouve au moins {max(missing + 4, 10)} hôtels ACTUELLEMENT OUVERTS et physiquement situés en {destination}, adaptés à ce profil.
Hôtels déjà retenus à ne pas répéter : {excluded}.

Exigences impératives :
- ne citer aucun hôtel situé dans un autre pays ;
- ne pas inclure un hôtel seulement annoncé ou encore en construction ;
- donner le vrai site officiel HTTPS de l'hôtel, et non une OTA, un blog ou un comparateur ;
- donner séparément une source HTTPS étayant l'existence, la localisation et l'adéquation au profil ;
- ne pas inventer de chambres communicantes, kids club, statut adults-only, piscine privée, spa ou restaurant ;
- si un critère familial n'est pas explicitement sourcé, ne pas l'affirmer ;
- donner aussi jusqu'à 3 conseils actuels pour ce profil et cette destination ;
- répondre en français avec des URLs complètes.
""".strip()

    result = api_post(
        "responses",
        {
            "model": RESEARCH_MODEL,
            "tools": [{"type": "web_search_preview"}],
            "tool_choice": "required",
            "input": prompt,
            "max_output_tokens": 9000,
        },
    )
    text = response_text(result)
    if not text:
        raise RuntimeError(f"Recherche vide pour {destination}/{profile}")
    return text


def extract_destination_profile(text, destination, profile):
    instructions = f"""
Transforme le texte source en JSON strict sans rien ajouter.
La seule destination autorisee est exactement : {destination}.
Le seul profil autorise est exactement : {profile}.

Retourne exactement :
{{
  "destination": "{destination}",
  "profile": "{profile}",
  "summary": "...",
  "practical_note": "...",
  "hotels": [
    {{
      "name": "...",
      "country": "{destination}",
      "location": "...",
      "description": "...",
      "official_url": "https://...",
      "source_url": "https://...",
      "source_publisher": "...",
      "published_at": "YYYY-MM-DD ou null"
    }}
  ],
  "advice": [
    {{
      "title": "...",
      "detail": "...",
      "source_url": "https://...",
      "source_publisher": "...",
      "published_at": "YYYY-MM-DD ou null"
    }}
  ]
}}

Regles :
- exclure tout hotel qui n'est pas physiquement situe en {destination};
- exclure tout hotel non encore ouvert ;
- official_url doit etre le domaine officiel de l'hotel ou de son groupe hotelier ;
- source_url doit etre presente dans le texte source ;
- ne pas transformer une page de blog, OTA ou comparateur en site officiel ;
- ne pas deduire un service familial ou romantique non explicite dans la source ;
- dates au format YYYY-MM-DD ou null.
""".strip()

    result = api_post(
        "chat/completions",
        {
            "model": EXTRACT_MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": text},
            ],
        },
    )
    return json.loads(result["choices"][0]["message"]["content"])


def collect_profile(item, profile, previous_profile):
    destination = item["destination"]
    retained = []

    # Les résultats web valides de l'exécution précédente sont conservés.
    for old in previous_profile.get("hotels", []):
        cleaned = clean_hotel(old, destination, profile)
        if cleaned:
            retained.append(cleaned)
    retained = unique_hotels(retained)[:TARGET_HOTELS]

    summary = previous_profile.get("summary") or item.get("summary", "")
    practical_note = previous_profile.get("practical_note") or item.get("practical", {}).get("fromParis", "")
    advice = previous_profile.get("advice", [])[:5]

    for pass_number in range(1, MAX_PASSES + 1):
        missing = TARGET_HOTELS - len(retained)
        if missing <= 0:
            break
        logging.info(
            "%s / %s : passe %d, %d hotel(s) manquant(s)",
            destination,
            profile,
            pass_number,
            missing,
        )
        try:
            text = research_destination_profile(
                item,
                profile,
                [h["name"] for h in retained],
                missing,
            )
            raw = extract_destination_profile(text, destination, profile)
            candidates = []
            for hotel in raw.get("hotels", []):
                cleaned = clean_hotel(hotel, destination, profile)
                if cleaned:
                    candidates.append(cleaned)
            retained = unique_hotels(retained + candidates)[:TARGET_HOTELS]

            fresh_advice = []
            for tip in raw.get("advice", []):
                cleaned = clean_advice(tip, destination, profile)
                if cleaned:
                    fresh_advice.append(cleaned)
            if fresh_advice:
                advice = fresh_advice[:5]
            if isinstance(raw.get("summary"), str) and raw["summary"].strip():
                summary = raw["summary"].strip()
            if isinstance(raw.get("practical_note"), str) and raw["practical_note"].strip():
                practical_note = raw["practical_note"].strip()
        except Exception as exc:
            logging.warning(
                "Passe %d ignoree pour %s/%s: %s",
                pass_number,
                destination,
                profile,
                exc,
            )

    return {
        "summary": summary,
        "practical_note": practical_note,
        "hotels": retained,
        "advice": advice,
        "complete": len(retained) == TARGET_HOTELS,
        "hotel_count": len(retained),
    }


def research_openings(existing_names, missing):
    excluded = ", ".join(existing_names) if existing_names else "aucun"
    prompt = f"""
Date UTC : {datetime.now(timezone.utc).date()}.
Recherche des ouvertures d'hotels de luxe dans le monde.
Trouve au moins {max(missing + 8, 20)} établissements récemment ouverts ou officiellement annoncés.
Exclus : {excluded}.

Pour chaque établissement, fournir : nom, pays, ville, date d'ouverture exacte ou annoncée,
site officiel HTTPS, source HTTPS, éditeur et résumé.
Ne pas inclure une simple rénovation, une nouvelle suite, un nouveau spa ou un hôtel sans date identifiable.
Le site officiel doit être distinct d'une OTA ou d'un blog. Réponds en français.
""".strip()
    result = api_post(
        "responses",
        {
            "model": RESEARCH_MODEL,
            "tools": [{"type": "web_search_preview"}],
            "tool_choice": "required",
            "input": prompt,
            "max_output_tokens": 10000,
        },
    )
    text = response_text(result)
    if not text:
        raise RuntimeError("Recherche d'ouvertures vide")
    return text


def extract_openings(text):
    instructions = """
Transforme le texte en JSON strict : {"hotel_openings": [...]}.
Chaque objet contient exactement : hotel_name, country, city, opened_in,
official_url, source_url, source_publisher, summary.
opened_in doit être YYYY-MM-DD. Exclure les entrées sans date, les rénovations,
les extensions et les simples changements de marque. N'invente rien.
official_url doit être le site officiel de l'hôtel ou de son groupe.
""".strip()
    result = api_post(
        "chat/completions",
        {
            "model": EXTRACT_MODEL,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": text},
            ],
        },
    )
    return json.loads(result["choices"][0]["message"]["content"])


def clean_opening(raw):
    required = (
        "hotel_name",
        "country",
        "city",
        "official_url",
        "source_url",
        "source_publisher",
        "summary",
    )
    if not all(isinstance(raw.get(k), str) and raw[k].strip() for k in required):
        return None
    opened_in = clean_date(raw.get("opened_in"))
    official_url = clean_url(raw.get("official_url"))
    source_url = clean_url(raw.get("source_url"))
    if not opened_in or not official_url or not source_url:
        return None
    return {
        "hotel_name": raw["hotel_name"].strip(),
        "country": raw["country"].strip(),
        "city": raw["city"].strip(),
        "opened_in": opened_in,
        "official_url": official_url,
        "source_url": source_url,
        "source_publisher": raw["source_publisher"].strip(),
        "summary": raw["summary"].strip(),
    }


def collect_openings(previous):
    openings = []
    for old in previous:
        cleaned = clean_opening(old)
        if cleaned:
            openings.append(cleaned)

    def deduplicate(values):
        result, seen = [], set()
        for value in values:
            key = normalise_name(value.get("hotel_name"))
            if key and key not in seen:
                seen.add(key)
                result.append(value)
        return result

    openings = deduplicate(openings)
    for pass_number in range(1, MAX_PASSES + 1):
        missing = TARGET_OPENINGS - len(openings)
        if missing <= 0:
            break
        logging.info("Ouvertures : passe %d, %d manquante(s)", pass_number, missing)
        try:
            text = research_openings([x["hotel_name"] for x in openings], missing)
            raw = extract_openings(text)
            fresh = []
            for value in raw.get("hotel_openings", []):
                cleaned = clean_opening(value)
                if cleaned:
                    fresh.append(cleaned)
            openings = deduplicate(openings + fresh)
        except Exception as exc:
            logging.warning("Passe ouvertures %d ignoree: %s", pass_number, exc)

    openings = sorted(openings, key=lambda x: x["opened_in"], reverse=True)[:TARGET_OPENINGS]
    for rank, opening in enumerate(openings, 1):
        opening["rank"] = rank
    return openings


def main():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("data/catalog.json doit contenir une liste non vide")

    old = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    old_items = {x.get("destination"): x for x in old.get("items", [])}
    items = []

    for item in catalog:
        destination = item["destination"]
        logging.info("Destination : %s", destination)
        old_profiles = old_items.get(destination, {}).get("profiles", {})
        profiles = {}

        for profile in ("couple", "family"):
            base_profile = item.get("profiles", {}).get(profile, {})
            collected = collect_profile(item, profile, old_profiles.get(profile, {}))
            profiles[profile] = base_profile | collected

        items.append(item | {"profiles": profiles})

    openings = collect_openings(old.get("hotel_openings", []))
    incomplete = []
    for item in items:
        for profile in ("couple", "family"):
            count = item["profiles"][profile]["hotel_count"]
            if count < TARGET_HOTELS:
                incomplete.append(
                    {"destination": item["destination"], "profile": profile, "count": count}
                )

    payload = {
        "schema_version": 4,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": "Atlas enrichi par des recherches indépendantes par pays et par profil.",
        "items": sorted(items, key=lambda x: x.get("score", 0), reverse=True),
        "hotel_openings": openings,
        "quality_report": {
            "target_hotels_per_profile": TARGET_HOTELS,
            "target_openings": TARGET_OPENINGS,
            "incomplete_profiles": incomplete,
            "opening_count": len(openings),
        },
        "methodology": {
            "research_scope": "one destination and one profile per search",
            "max_passes": MAX_PASSES,
            "cross_country_filter": True,
            "availability": "not verified",
        },
    }

    tmp = OUTPUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(OUTPUT)

    logging.info("data/trends.json mis a jour")
    logging.info("Profils incomplets : %d", len(incomplete))
    logging.info("Ouvertures conservees : %d", len(openings))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Echec de la mise a jour")
        sys.exit(1)
