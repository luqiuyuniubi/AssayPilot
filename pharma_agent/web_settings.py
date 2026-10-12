"""Optional search credentials, independent of model credentials; never public or exported."""
import base64,json,os,threading
from pathlib import Path
from model_settings import protect
PATH=Path(__file__).resolve().parent/'.local'/'web.json'
LOCK=threading.Lock()
PROVIDERS={'public':{'label':'公开搜索（免密钥，稳定性有限）','requires_key':False},
 'tavily':{'label':'Tavily Search','requires_key':True},'brave':{'label':'Brave Search','requires_key':True}}
def load_saved():
    if not PATH.exists():return None
    try:
        c=json.loads(PATH.read_text(encoding='utf-8'))
        c['api_key']=protect(base64.b64decode(c.pop('encrypted_key')),True).decode()
        return c
    except Exception:return None
RUNTIME=load_saved()
def effective():
    with LOCK:
        if RUNTIME is not None:return dict(RUNTIME)
    return {'provider':os.environ.get('PHARMA_SEARCH_PROVIDER','public'),
        'api_key':os.environ.get('PHARMA_SEARCH_API_KEY',''),'remember':False}
def public():
    c=effective()
    return {'provider':c['provider'],'has_key':bool(c['api_key']),'remember':c['remember'],'providers':PROVIDERS}
def save(body):
    global RUNTIME
    previous=effective();provider=body.get('provider','public')
    if provider not in PROVIDERS:raise ValueError('搜索服务无效。')
    key=str(body.get('api_key','')).strip()
    if not key and provider==previous['provider']:key=previous['api_key']
    if provider=='public':key=''
    if PROVIDERS[provider]['requires_key'] and not key:raise ValueError('该搜索服务需要对应的API Key。')
    if any(x in key for x in '\r\n'):raise ValueError('搜索密钥格式无效。')
    c={'provider':provider,'api_key':key,'remember':bool(body.get('remember'))}
    if c['remember']:
        encrypted={k:v for k,v in c.items() if k!='api_key'}
        encrypted['encrypted_key']=base64.b64encode(protect(key.encode())).decode()
        PATH.parent.mkdir(exist_ok=True);tmp=PATH.with_suffix('.tmp')
        tmp.write_text(json.dumps(encrypted),encoding='utf-8');tmp.replace(PATH)
    elif PATH.exists():PATH.unlink()
    with LOCK:RUNTIME=c
    return public()
