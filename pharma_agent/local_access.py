"""Per-process local capability, opened by launcher via URL fragment; never sent to AI/providers."""
import base64,json,secrets,threading,time
from collections import deque
from pathlib import Path
from urllib.parse import urlparse
from model_settings import protect
ROOT=Path(__file__).resolve().parent
ACCESS_TOKEN=secrets.token_urlsafe(32)
API_SLOTS=threading.BoundedSemaphore(4)
RATE_LOCK=threading.Lock();RATES={}
def access_path(port):return ROOT/'.local'/('access-'+str(port)+'.json')
def save_access(port,version):
    path=access_path(port);path.parent.mkdir(exist_ok=True)
    payload=json.dumps({'version':version,'port':port,'token':ACCESS_TOKEN}).encode()
    encrypted=base64.b64encode(protect(payload)).decode()
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps({'encrypted':encrypted}),encoding='utf-8');tmp.replace(path)
def load_access(port,version=None):
    try:
        wrapper=json.loads(access_path(port).read_text(encoding='utf-8'))
        c=json.loads(protect(base64.b64decode(wrapper['encrypted']),True).decode())
        if c.get('port')==port and (version is None or c.get('version')==version):return c['token']
    except (ValueError,OSError,KeyError):pass
    return None
def remove_access(port):
    path=access_path(port)
    try:
        if load_access(port)==ACCESS_TOKEN:path.unlink()
    except (ValueError,OSError):pass
def validate_headers(headers,port,api=False):
    """Host validation prevents browser DNS rebinding even when no Origin is present."""
    allowed={'127.0.0.1:'+str(port),'localhost:'+str(port)}
    host=headers.get('Host','').lower()
    if host not in allowed:return 403,'请求地址不是本机服务。'
    origin=headers.get('Origin')
    if origin is not None:
        try:
            parsed=urlparse(origin)
            valid=parsed.scheme=='http' and parsed.netloc.lower()==host and parsed.hostname in ('127.0.0.1','localhost') and parsed.port==port and not parsed.path and not parsed.query and not parsed.fragment
        except ValueError:valid=False
        if not valid:return 403,'不接受跨来源请求。'
    if headers.get('Sec-Fetch-Site')=='cross-site':return 403,'不接受跨网站请求。'
    if api:
        supplied=headers.get('X-AssayPilot-Token','')
        if not isinstance(supplied,str) or not secrets.compare_digest(supplied,ACCESS_TOKEN):return 401,'请从“启动项目.cmd”打开本地工作台。'
    return None

def rate_allow(key,limit,window=60):
    now=time.monotonic()
    with RATE_LOCK:
        if len(RATES)>2000:
            for old in list(RATES):
                if not RATES[old] or now-RATES[old][-1]>window:RATES.pop(old,None)
        queue=RATES.setdefault(key,deque())
        while queue and now-queue[0]>window:queue.popleft()
        if len(queue)>=limit:return False
        queue.append(now);return True
