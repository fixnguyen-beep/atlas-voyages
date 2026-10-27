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
CATALOG = ROOT / 'data' / 'catalog.json'
OUTPUT = ROOT / 'data' / 'trends.json'
MODEL_RESEARCH = os.getenv('OPENAI_RESEARCH_MODEL', 'gpt-4.1-mini')
MODEL_EXTRACT = os.getenv('OPENAI_EXTRACT_MODEL', 'gpt-4o-mini')
API_URL = 'https://api.openai.com/v1'
TIMEOUT = 150
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def api_post(path, payload):
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise RuntimeError('OPENAI_API_KEY absent')
    r = requests.post(f'{API_URL}/{path}', headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}, json=payload, timeout=TIMEOUT)
    if not r.ok:
        raise RuntimeError(f'OpenAI HTTP {r.status_code}: {r.text[:700]}')
    return r.json()


def response_text(result):
    chunks = []
    for item in result.get('output', []):
        if item.get('type') == 'message':
            for part in item.get('content', []):
                if part.get('type') == 'output_text':
                    chunks.append(part.get('text', ''))
    return '\n'.join(chunks)


def research(destinations):
    prompt = (f"Date UTC: {datetime.now(timezone.utc).date()}. Recherche sur le web des faits publiés durant les 45 derniers jours "
              'sur le tourisme haut de gamme, les nouvelles ouvertures hôtelières, les liaisons aériennes, les changements de fréquentation '
              'et les destinations émergentes. Privilégie les offices de tourisme, hôtels, compagnies aériennes et études sectorielles. '
              'Ne présente jamais une tendance comme mesurée sans chiffre et source. '
              'N’invente ni hôtel, ni prix, ni statistiques. Réponds en français. '
              f'Destinations couvertes : {", ".join(destinations)}. '
              'Fournis au plus 12 informations concrètes avec URL complète, éditeur et date de publication; '
              'ignore les informations non corroborées. Si aucune information fiable, indique-le.')
    result = api_post('responses', {
        'model': MODEL_RESEARCH,
        'tools': [{'type': 'web_search_preview'}],
        'tool_choice': 'required',
        'input': prompt,
        'max_output_tokens': 3500,
    })
    raw = response_text(result)
    if not raw.strip():
        raise RuntimeError('Recherche web sans texte de réponse')
    return raw


def extract(research_text, destinations):
    instructions = ('Convertis les informations de recherche en JSON strict. Ne crée aucune information absente du texte. '
                    'Chaque signal doit porter sur une destination de la liste, citer une URL HTTP(S) réelle mentionnée dans le texte, '
                    'et décrire un fait concret. Ne crée pas de scores de popularité ni de prix. '
                    'Réponds avec un objet {"signals": [...]}. Chaque signal contient exactement '
                    'destination, title, detail, publisher, url, published_at (YYYY-MM-DD ou null). '
                    'Maximum 12 signaux. Ne cite pas de source si tu ne peux pas fournir son URL. '
                    f'Destinations permises: {json.dumps(destinations, ensure_ascii=False)}.')
    result = api_post('chat/completions', {
        'model': MODEL_EXTRACT,
        'temperature': 0,
        'response_format': {'type': 'json_object'},
        'messages': [{'role': 'system', 'content': instructions},
                     {'role': 'user', 'content': research_text}],
    })
    return json.loads(result['choices'][0]['message']['content'])


def valid_url(url):
    try:
        p = urlparse(url)
        return p.scheme == 'https' and bool(p.netloc) and not p.username and not p.password
    except (TypeError, ValueError):
        return False


def clean_signals(raw, allowed):
    signals = []
    seen = set()
    for s in raw.get('signals', [])[:12]:
        if not isinstance(s, dict):
            continue
        if s.get('destination') not in allowed or not valid_url(s.get('url')):
            continue
        if not all(isinstance(s.get(k), str) and s[k].strip() for k in ('title', 'detail', 'publisher')):
            continue
        date = s.get('published_at')
        if date is not None and (not isinstance(date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date)):
            date = None
        key = (s['destination'], s['url'])
        if key in seen:
            continue
        seen.add(key)
        signals.append({k: s.get(k) for k in ('destination', 'title', 'detail', 'publisher', 'url') } | {'published_at': date, 'verified': False})
    return signals


def main():
    if not CATALOG.exists():
        raise FileNotFoundError('data/catalog.json absent : exécuter scripts/migrate_catalog.py une fois')
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    if not isinstance(catalog, list) or not catalog:
        raise ValueError('data/catalog.json doit être une liste non vide')
    destinations = [x['destination'] for x in catalog]
    if len(destinations) != len(set(destinations)):
        raise ValueError('Destinations en double dans catalog.json')
    logging.info('Recherche web pour %d destinations', len(destinations))
    raw = research(destinations)
    signals = clean_signals(extract(raw, destinations), set(destinations))
    logging.info('%d signaux avec URL; liens non vérifiés indépendamment', len(signals))
    # Conserver la dernière version publiée si aucune nouveauté fiable.
    if not signals:
        logging.warning('Aucun signal retenu : trends.json inchangé')
        return
    old = json.loads(OUTPUT.read_text(encoding='utf-8')) if OUTPUT.exists() else {}
    old_signals = old.get('signals', [])
    old_keys = {(s.get('destination'), s.get('url')) for s in old_signals}
    merged = signals + [s for s in old_signals if (s.get('destination'), s.get('url')) not in {(n['destination'], n['url']) for n in signals}]
    merged = merged[:30]
    # Ne changer generated_at que si les faits changent réellement.
    if merged == old_signals:
        logging.info('Aucun changement : trends.json inchangé')
        return
    featured = []
    for item in catalog:
        associated = next((s for s in signals if s['destination'] == item['destination']), None)
        if associated:
            featured.append({'destination': item['destination'], 'theme': item.get('theme', ''),
                             'score': item.get('score'), 'reason': associated['detail']})
        if len(featured) >= 5:
            break
    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'summary': f'{len(signals)} actualités touristiques sourcées identifiées. Consultez les sources avant réservation.',
        'featured': featured or old.get('featured', []),
        'items': sorted(catalog, key=lambda x: x.get('score', 0), reverse=True),
        'signals': merged,
        'methodology': {'research_window_days': 45, 'scores': 'editorial_static_not_trend_measure',
                        'sources': 'AI-assisted web research; URLs not independently verified'},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(OUTPUT)
    logging.info('Fichier mis à jour')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        logging.exception('Échec de la mise à jour')
        sys.exit(1)
