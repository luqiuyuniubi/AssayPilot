"""Bounded public-page HTTP reader with DNS/IP validation and pinned connection addresses."""
import http.client,ipaddress,socket,ssl
from urllib.parse import urlparse,urljoin

class PublicWebError(RuntimeError):pass
def validate_public_url(url):
    if not isinstance(url,str) or len(url)>2500 or any(x in url for x in ('\r','\n','\\')):raise PublicWebError('网址格式无效。')
    try:p=urlparse(url);port=p.port
    except ValueError:raise PublicWebError('网址格式无效。') from None
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:raise PublicWebError('只允许没有用户名和密码的公开HTTP(S)网页。')
    if port not in (None,80,443):raise PublicWebError('只允许公开网页的标准端口。')
    host=p.hostname.lower().rstrip('.')
    if host in ('localhost','metadata.google.internal') or host.endswith(('.localhost','.local','.internal','.lan')):raise PublicWebError('不能读取本机或内网网页。')
    try:
        ip=ipaddress.ip_address(host)
        if not ip.is_global or ip.is_multicast or ip.is_reserved or getattr(ip,'ipv4_mapped',None) and not ip.ipv4_mapped.is_global:raise PublicWebError('不能读取私有或保留地址。')
    except ValueError:pass
    try:addresses=socket.getaddrinfo(host,port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM)
    except socket.gaierror:raise PublicWebError('网页域名无法解析。') from None
    ips=[]
    for _,_,_,_,address in addresses:
        ip=ipaddress.ip_address(address[0])
        if not ip.is_global or ip.is_multicast or ip.is_reserved or getattr(ip,'ipv4_mapped',None) and not ip.ipv4_mapped.is_global:raise PublicWebError('网页解析到了非公开地址，已阻止访问。')
        if address[0] not in ips:ips.append(address[0])
    if not ips:raise PublicWebError('网页域名没有有效公开地址。')
    return p,sorted(ips,key=lambda x:':' in x)

def request_public(url,headers=None,body=None,max_bytes=2*1024*1024):
    current=url
    for redirect in range(5):
        parsed,ips=validate_public_url(current)
        port=parsed.port or (443 if parsed.scheme=='https' else 80)
        conn=None
        try:
            connection=http.client.HTTPSConnection if parsed.scheme=='https' else http.client.HTTPConnection
            conn=connection(parsed.hostname,port,timeout=15)
            # TLS verifies the original DNS name, while the socket uses a validated public IP.
            def connect(address,timeout=15,source_address=None,**kwargs):
                return socket.create_connection((ips[0],port),timeout,source_address)
            conn._create_connection=connect
            target=(parsed.path or '/')+('?'+parsed.query if parsed.query else '')
            req_headers={'User-Agent':'Mozilla/5.0 (compatible; AssayPilot/1.7; public research reader)','Accept-Encoding':'identity',**(headers or {})}
            conn.request('POST' if body is not None else 'GET',target,body=body,headers=req_headers)
            response=conn.getresponse()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location:raise PublicWebError('网页跳转缺少目标。')
                next_url=urljoin(current,location)
                # Never forward service credentials or private POST bodies across redirects.
                if body is not None or any(k.lower() in ('authorization','x-subscription-token') for k in req_headers):raise PublicWebError('带密钥的搜索接口不允许跳转。')
                current=next_url;continue
            if response.status>=400:raise PublicWebError('网页或接口返回HTTP '+str(response.status)+'。')
            content=response.read(max_bytes+1)
            if len(content)>max_bytes:raise PublicWebError('网页内容超过读取大小限制。')
            return content,dict(response.getheaders()),current
        except (socket.timeout,TimeoutError):raise PublicWebError('网页或接口读取超时。') from None
        except (OSError,http.client.HTTPException,ssl.SSLError):raise PublicWebError('网页或接口暂时无法连接。') from None
        finally:
            if conn:conn.close()
    raise PublicWebError('网页跳转次数过多。')
