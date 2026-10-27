"""À exécuter une fois, depuis la racine du dépôt, avant la nouvelle mise à jour."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'data' / 'trends.json'
target = root / 'data' / 'catalog.json'
if target.exists():
    raise SystemExit('catalog.json existe déjà; aucune modification')
if not source.exists():
    raise SystemExit('data/trends.json introuvable')
items = json.loads(source.read_text(encoding='utf-8'))['items']
if not isinstance(items, list) or not items:
    raise SystemExit('items absent ou vide')
target.write_text(json.dumps(items, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'Créé {target} avec {len(items)} destinations')
