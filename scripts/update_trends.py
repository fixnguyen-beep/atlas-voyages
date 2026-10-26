import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

OUTPUT_PATH = Path("data/trends.json")
OUTPUT_PATH.parent.mkdir(exist_ok=True)

BASE_ITEMS = [
    {
        "destination": "Thaïlande",
        "trend": "Hausse du luxe durable à Bangkok et Koh Samui",
        "score": 92,
        "source": "travel-insights"
    },
    {
        "destination": "Japon",
        "trend": "Demande stable pour Kyoto, Tokyo et les séjours hors saison",
        "score": 87,
        "source": "travel-insights"
    },
    {
        "destination": "Maroc",
        "trend": "Marrakech et Essaouira attirent davantage les voyageurs culturels",
        "score": 84,
        "source": "travel-insights"
    },
    {
        "destination": "Portugal",
        "trend": "Croissance du tourisme de niche autour du design et du bien-être",
        "score": 80,
        "source": "travel-insights"
    },
    {
        "destination": "Islande",
        "trend": "Toujours forte demande pour les circuits nature et les hôtels premium",
        "score": 78,
        "source": "travel-insights"
    }
]


def fetch_sources():
    """Return the raw trend inputs. Replace this logic later with RSS/API sources."""
    return BASE_ITEMS


def ask_llm(payload):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": "Les tendances les plus fortes restent le luxe durable, les voyages culturels et les destinations nature.",
            "items": payload,
        }

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": "Tu es un analyste de tendances de voyage en français. Donne un résumé concis et utile pour un site de recommandations de destinations."
            },
            {
                "role": "user",
                "content": f"Voici les tendances brutes: {json.dumps(payload, ensure_ascii=False)}. Donne-moi un résumé en français de 2 à 3 phrases et un classement utile pour un site de voyage."
            }
        ],
        "temperature": 0.7,
    }

    try:
        response = requests.post(url, headers=headers, json=body, timeout=60)
        response.raise_for_status()
        result = response.json()
        summary = result["choices"][0]["message"]["content"].strip()
    except Exception:
        summary = "Les tendances les plus fortes restent le luxe durable, les voyages culturels et les destinations nature."

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "items": payload,
    }


def main():
    payload = fetch_sources()
    data = ask_llm(payload)
    OUTPUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
