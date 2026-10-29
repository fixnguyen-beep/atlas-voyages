import json, logging, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
ROOT=Path(__file__).resolve().parents[1]; CATALOG=ROOT/'data/catalog.json'; OUTPUT=ROOT/'data/trends.json'
API='https://api.openai.com/v1'; RESEARCH=os.getenv('OPENAI_RESEARCH_MODEL','gpt-4.1-mini'); EXTRACT=os.getenv('OPENAI_EXTRACT_MODEL','gpt-4o-mini'); BATCH=int(os.getenv('ATLAS_BATCH_SIZE','2'))
logging.basicConfig(level=logging.INFO,format='%(levelname)s: %(message)s')
def post(path,payload):
 key=os.getenv('OPENAI_API_KEY')
 if not key: raise RuntimeError('Secret OPENAI_API_KEY absent')
 r=requests.post(f'{API}/{path}',headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},json=payload,timeout=240)
 if not r.ok: raise RuntimeError(f'OpenAI HTTP {r.status_code}: {r.text[:900]}')
 return r.json()
def outtext(r):
 return '\n'.join(p.get('text','') for x in r.get('output',[]) if x.get('type')=='message' for p in x.get('content',[]) if p.get('type')=='output_text')
def valid_url(v):
 try: u=urlparse(v); return u.scheme=='https' and bool(u.netloc)
 except: return False
def date(v): return v if isinstance(v,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',v) else None
def research(batch):
 brief=[{'destination':x['destination'],'couple':x['profiles']['couple']['angle'],'family':x['profiles']['family']['angle']} for x in batch]
 prompt=f'''Date UTC : {datetime.now(timezone.utc).date()}.
Recherche sur le web, pour chaque destination de {json.dumps(brief,ensure_ascii=False)} :
- exactement 10 hôtels actuellement ouverts adaptés à un voyage EN COUPLE ;
- exactement 10 hôtels actuellement ouverts adaptés à un voyage EN FAMILLE ;
- conseils actuels distincts pour chaque profil ;
- ouvertures d'hôtels de luxe récentes ou officiellement annoncées.
Un même hôtel peut figurer dans les deux profils seulement s'il est réellement pertinent pour les deux, mais les descriptions doivent expliquer l'adéquation au profil.
Priorité aux sites officiels des hôtels, offices de tourisme, compagnies aériennes et médias professionnels reconnus. Ne fabrique ni disponibilité, ni prix, ni date. Chaque hôtel et ouverture doit avoir un site officiel HTTPS et une source HTTPS. Réponds en français.'''
 r=post('responses',{'model':RESEARCH,'tools':[{'type':'web_search_preview'}],'tool_choice':'required','input':prompt,'max_output_tokens':14000})
 t=outtext(r)
 if not t: raise RuntimeError('Recherche vide')
 return t
def extract(text,allowed):
 system=f'''Transforme le texte en JSON strict sans rien inventer. Destinations autorisées : {json.dumps(sorted(allowed),ensure_ascii=False)}.
Objet attendu : {{"destinations":[{{"destination":"...","profiles":{{"couple":{{"hotels":[10 objets],"advice":[objets],"summary":"...","practical_note":"..."}},"family":{{même structure}}}}}}],"hotel_openings":[objets]}}.
Hôtel : name, location, description, official_url, source_url, source_publisher, published_at. Conseil : title, detail, source_url, source_publisher, published_at. Ouverture : hotel_name, country, city, opened_in, official_url, source_url, source_publisher, summary.
URLs HTTPS obligatoires et présentes dans le texte. Dates YYYY-MM-DD ou null. Exclure toute entrée non étayée.'''
 r=post('chat/completions',{'model':EXTRACT,'temperature':0,'response_format':{'type':'json_object'},'messages':[{'role':'system','content':system},{'role':'user','content':text}]})
 return json.loads(r['choices'][0]['message']['content'])
def clean_hotel(h):
 req=('name','location','description','official_url','source_url','source_publisher')
 if not all(isinstance(h.get(k),str) and h[k].strip() for k in req) or not valid_url(h['official_url']) or not valid_url(h['source_url']): return None
 return {k:h[k].strip() for k in req}|{'published_at':date(h.get('published_at')),'status':'web_researched'}
def clean_advice(a):
 req=('title','detail','source_url','source_publisher')
 if not all(isinstance(a.get(k),str) and a[k].strip() for k in req) or not valid_url(a['source_url']): return None
 return {k:a[k].strip() for k in req}|{'published_at':date(a.get('published_at'))}
def clean(raw,allowed):
 destinations={}; openings=[]
 for d in raw.get('destinations',[]):
  name=d.get('destination')
  if name not in allowed: continue
  profiles={}
  for mode in ('couple','family'):
   p=d.get('profiles',{}).get(mode,{})
   hotels=[x for h in p.get('hotels',[]) if (x:=clean_hotel(h))][:10]
   advice=[x for a in p.get('advice',[]) if (x:=clean_advice(a))][:5]
   profiles[mode]={'summary':p.get('summary',''),'practical_note':p.get('practical_note',''),'hotels':hotels,'advice':advice}
  destinations[name]=profiles
 for o in raw.get('hotel_openings',[]):
  req=('hotel_name','country','city','official_url','source_url','source_publisher','summary')
  if all(isinstance(o.get(k),str) and o[k].strip() for k in req) and valid_url(o['official_url']) and valid_url(o['source_url']):
   openings.append({k:o[k].strip() for k in req}|{'opened_in':date(o.get('opened_in'))})
 return destinations,openings
def fallback_hotels(item):
 result=[]
 for e in item.get('editorial_stays',[]):
  p=e.split('|',2)
  if len(p)==3: result.append({'name':p[0],'location':p[1],'description':p[2],'status':'editorial'})
 return result
def main():
 catalog=json.load(open(CATALOG,encoding='utf-8')); allowed={x['destination'] for x in catalog}
 old=json.load(open(OUTPUT,encoding='utf-8')) if OUTPUT.exists() else {}; olditems={x.get('destination'):x for x in old.get('items',[])}
 dynamic={}; openings=[]
 for i in range(0,len(catalog),BATCH):
  batch=catalog[i:i+BATCH]; logging.info('Recherche %s',', '.join(x['destination'] for x in batch))
  d,o=clean(extract(research(batch),allowed),allowed); dynamic.update(d); openings.extend(o)
 items=[]
 for item in catalog:
  name=item['destination']; profiles={}
  for mode in ('couple','family'):
   fresh=dynamic.get(name,{}).get(mode,{}); prev=olditems.get(name,{}).get('profiles',{}).get(mode,{})
   hotels=fresh.get('hotels') or prev.get('hotels') or fallback_hotels(item)
   profiles[mode]=item['profiles'][mode]|{'summary':fresh.get('summary') or prev.get('summary') or item['summary'],'practical_note':fresh.get('practical_note') or prev.get('practical_note') or item['practical']['fromParis'],'hotels':hotels[:10],'advice':(fresh.get('advice') or prev.get('advice') or [])[:5]}
  items.append(item|{'profiles':profiles})
 unique=[]; seen=set()
 for o in openings+old.get('hotel_openings',[]):
  k=(o.get('hotel_name','').casefold(),o.get('country','').casefold())
  if k not in seen: seen.add(k); unique.append(o)
 unique=sorted(unique,key=lambda x:x.get('opened_in') or '0000-00-00',reverse=True)[:20]
 for i,o in enumerate(unique,1): o['rank']=i
 payload={'schema_version':3,'generated_at':datetime.now(timezone.utc).isoformat(),'summary':'Atlas éditorial enrichi par une recherche web sourcée, avec sélections distinctes couple et famille.','items':sorted(items,key=lambda x:x.get('score',0),reverse=True),'hotel_openings':unique,'methodology':{'hotels_per_destination_per_profile':10,'hotel_openings_count':20,'availability':'not verified'}}
 tmp=OUTPUT.with_suffix('.tmp'); tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(OUTPUT)
if __name__=='__main__':
 try: main()
 except Exception: logging.exception('Échec'); sys.exit(1)
