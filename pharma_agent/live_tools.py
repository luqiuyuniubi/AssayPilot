"""Read-only weather and news retrieval. Fixed endpoints; no assay input or credential sharing."""
import concurrent.futures,html,json,math,re,threading,time,urllib.error,urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode,urlparse

TZ=timezone(timedelta(hours=8))
def now():return datetime.now(TZ)
def stamp():return now().isoformat(timespec='seconds')
FEEDS={
    '综合':'https://www.chinanews.com.cn/rss/scroll-news.xml',
    '要闻':'https://www.chinanews.com.cn/rss/importnews.xml',
    '国际':'https://www.chinanews.com.cn/rss/world.xml',
    '财经':'https://www.chinanews.com.cn/rss/finance.xml',
    '健康':'https://www.chinanews.com.cn/rss/jk.xml',
    '体育':'https://www.chinanews.com.cn/rss/sports.xml',
}
ALLOWED={'api.open-meteo.com','geocoding-api.open-meteo.com','www.chinanews.com.cn'}
CITY_ALIASES={'南京':'Nanjing','北京':'Beijing','上海':'Shanghai','广州':'Guangzhou','深圳':'Shenzhen','杭州':'Hangzhou','苏州':'Suzhou','成都':'Chengdu','武汉':'Wuhan','西安':'Xian','重庆':'Chongqing','天津':'Tianjin','香港':'Hong Kong','台北':'Taipei','伦敦':'London','东京':'Tokyo','纽约':'New York'}
WEATHER_TEXT={0:'晴',1:'大部晴朗',2:'局部多云',3:'阴',45:'雾',48:'冻雾',51:'小毛毛雨',53:'毛毛雨',55:'较强毛毛雨',56:'冻毛毛雨',57:'强冻毛毛雨',61:'小雨',63:'中雨',65:'大雨',66:'冻雨',67:'强冻雨',71:'小雪',73:'中雪',75:'大雪',77:'雪粒',80:'小阵雨',81:'阵雨',82:'强阵雨',85:'小阵雪',86:'强阵雪',95:'雷雨',96:'雷雨伴冰雹',99:'强雷雨伴冰雹'}
CACHE={};LOCK=threading.Lock()

class LiveToolError(RuntimeError):pass
class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        parsed=urlparse(newurl)
        if parsed.scheme!='https' or parsed.hostname not in ALLOWED:raise LiveToolError('数据源跳转到未授权地址。')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(url,ttl=120):
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname not in ALLOWED:raise LiveToolError('只允许访问已配置的公开数据源。')
    with LOCK:
        cached=CACHE.get(url)
        if cached and time.monotonic()-cached[0]<ttl:return cached[1],cached[2]
    request=urllib.request.Request(url,headers={'User-Agent':'AssayPilot/1.6 (local interview demo)','Accept':'application/json,application/rss+xml,text/xml'})
    try:
        with urllib.request.build_opener(SafeRedirect()).open(request,timeout=12) as response:
            data=response.read(3*1024*1024+1)
        if len(data)>3*1024*1024:raise LiveToolError('数据源响应超过大小限制。')
    except urllib.error.HTTPError as e:raise LiveToolError('数据源返回HTTP '+str(e.code)+'，暂时无法查询。') from None
    except (urllib.error.URLError,TimeoutError):raise LiveToolError('联网查询失败或超时，请检查本机网络后重试。') from None
    queried_at=stamp()
    with LOCK:
        if len(CACHE)>100:CACHE.clear()
        CACHE[url]=(time.monotonic(),data,queried_at)
    return data,queried_at

def get_json(url,ttl=120):
    raw,queried=fetch(url,ttl)
    try:return json.loads(raw),queried
    except (ValueError,TypeError):raise LiveToolError('数据源未返回有效JSON。') from None

def get_weather(location,days=1,day_offset=0):
    if not isinstance(location,str) or not 1<=len(location.strip())<=80:raise ValueError('请提供城市名称。')
    if type(days) is not int or type(day_offset) is not int or not 1<=days<=7 or not 0<=day_offset<=6:raise ValueError('当前支持未来7天内起始、连续1–7天的天气。')
    name=location.strip().removesuffix('市')
    query=CITY_ALIASES.get(name,name)
    geourl='https://geocoding-api.open-meteo.com/v1/search?'+urlencode({'name':query,'count':5,'language':'zh','format':'json'})
    geo,_=get_json(geourl,86400)
    candidates=geo.get('results') or []
    if not candidates:return {'needs_location':True,'message':'未找到这个城市，请补充城市和省份/国家。','queried_at':stamp()}
    # Prefer a named main city by population; show resolved location to avoid hidden geocoding assumptions.
    candidates=sorted(candidates,key=lambda x:x.get('population',0),reverse=True)
    city=candidates[0]
    if name not in CITY_ALIASES and len(candidates)>1:
        second=candidates[1]
        if city.get('country_code')!=second.get('country_code') and city.get('population',0)<2*second.get('population',0):
            return {'needs_location':True,'message':'这个地名有多个匹配，请补充国家或省份。','candidates':[x.get('name','')+' / '+x.get('country','')+' / '+x.get('admin1','') for x in candidates[:3]],'queried_at':stamp()}
    lat,lon=city['latitude'],city['longitude']
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (lat,lon)):raise LiveToolError('位置数据无效。')
    source='https://api.open-meteo.com/v1/forecast?'+urlencode({'latitude':lat,'longitude':lon,
        'current':'temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m',
        'daily':'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max',
        'timezone':'auto','forecast_days':days+day_offset})
    data,queried=get_json(source,120)
    current=data.get('current') or {};daily=data.get('daily') or {}
    forecasts=[]
    dates=daily.get('time') or []
    for i in range(day_offset,min(len(dates),day_offset+days)):
        def value(k):return (daily.get(k) or [None]*len(dates))[i]
        forecasts.append({'date':dates[i],'description':WEATHER_TEXT.get(value('weather_code'),'未知天气类型'),
            'temperature_min_c':value('temperature_2m_min'),'temperature_max_c':value('temperature_2m_max'),
            'precipitation_probability_max_pct':value('precipitation_probability_max')})
    if not forecasts:raise LiveToolError('没有取得所需日期的天气预报。')
    return {'provider':'Open-Meteo','location':city.get('name',name),'region':city.get('admin1',''),
        'country':city.get('country',''),'timezone':data.get('timezone'),
        'current':{'time':current.get('time'),'temperature_c':current.get('temperature_2m'),
        'feels_like_c':current.get('apparent_temperature'),'humidity_pct':current.get('relative_humidity_2m'),
        'wind_kmh':current.get('wind_speed_10m'),'description':WEATHER_TEXT.get(current.get('weather_code'),'未知天气类型')},
        'forecast':forecasts,'source_url':source,'queried_at':queried,'note':'当前值来自天气模型，预报可能变化；并非气象站实时观测或预警服务。'}

def safe_link(url):
    try:
        p=urlparse(url)
        return p.scheme in ('https','http') and bool(p.hostname) and not p.username and not p.password and '\n' not in url and '\r' not in url
    except ValueError:return False

def clean_text(value):return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>','',value or ''))).strip()
def parse_news(raw,source,queried):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise LiveToolError('订阅源包含不支持的XML声明。')
    try:root=ET.fromstring(raw)
    except ET.ParseError:raise LiveToolError('新闻源未返回有效RSS。') from None
    result=[]
    for item in root.findall('.//item'):
        title=clean_text(item.findtext('title'))[:250];link=(item.findtext('link') or '').strip()
        if not title or not safe_link(link):continue
        try:
            published=parsedate_to_datetime(item.findtext('pubDate') or '')
            if not published.tzinfo:published=published.replace(tzinfo=TZ)
            published=published.astimezone(TZ)
        except (ValueError,TypeError):continue  # Unknown dates cannot qualify as recent news.
        result.append({'title':title,'url':link,'published_at':published.isoformat(timespec='seconds'),
            'publisher':'中国新闻网','feed':source,'queried_at':queried})
    return result

def search_news(topic='',category='综合',limit=5,since_days=1):
    if not isinstance(topic,str) or len(topic)>80 or category not in FEEDS:raise ValueError('新闻主题或类别无效。')
    if type(limit) is not int or not 1<=limit<=8 or type(since_days) is not int or not 1<=since_days<=7:raise ValueError('新闻条数或时间范围无效。')
    feeds=[FEEDS[category]]
    if topic.strip():feeds=list(dict.fromkeys(feeds+[FEEDS['综合'],FEEDS['要闻'],FEEDS['健康'],FEEDS['财经']]))
    errors=[];items=[];retrieved=[]
    def read(source):
        raw,queried=fetch(source,120)
        return parse_news(raw,source,queried),queried
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(read,url) for url in feeds]
        for future in futures:
            try:
                articles,queried=future.result();items.extend(articles);retrieved.append(queried)
            except LiveToolError as e:errors.append(str(e))
    if not retrieved:raise LiveToolError('新闻源暂时无法访问，请稍后重试。')
    cutoff=now()-timedelta(days=since_days)
    keywords=[x for x in re.split(r'[\s,，、]+',topic.strip()) if x]
    unique={}
    for item in items:
        published=datetime.fromisoformat(item['published_at'])
        if not cutoff<=published<=now()+timedelta(minutes=10):continue
        if keywords and not any(k.lower() in item['title'].lower() for k in keywords):continue
        unique[item['url']]=item
    articles=sorted(unique.values(),key=lambda x:x['published_at'],reverse=True)[:limit]
    return {'provider':'中国新闻网官方RSS','topic':topic,'category':category,'since_days':since_days,
        'articles':articles,'queried_at':max(retrieved),'partial_failures':errors,
        'note':'仅检索上述新闻订阅的近期标题，非全网搜索或新闻全文；发布时间与事件发生时间可能不同。'}

LIVE_TOOLS=[
 {'type':'function','function':{'name':'get_weather','description':'查询指定城市的当前天气模型数据和未来预报；必须先取得城市，不能猜用户位置。',
  'parameters':{'type':'object','properties':{'location':{'type':'string','description':'城市，可加省份或国家'},'days':{'type':'integer','minimum':1,'maximum':7},'day_offset':{'type':'integer','minimum':0,'maximum':6}},'required':['location','days','day_offset'],'additionalProperties':False}}},
 {'type':'function','function':{'name':'search_news','description':'检索中国新闻网官方RSS近期标题、发布时间和原文链接。不是全网检索；没有匹配时如实说明。',
  'parameters':{'type':'object','properties':{'topic':{'type':'string','description':'标题关键词，综合最新新闻用空字符串'},'category':{'type':'string','enum':list(FEEDS)},'limit':{'type':'integer','minimum':1,'maximum':8},'since_days':{'type':'integer','minimum':1,'maximum':7}},'required':['topic','category','limit','since_days'],'additionalProperties':False}}},
]

def fallback_plan(question,history=None):
    q=question.strip();recent=next((x.get('content','') for x in reversed(history or []) if x.get('role')=='user' and x.get('intent')=='realtime'),'')
    if re.search(r'天气|气温|下雨|weather|forecast',q,re.I) or re.search(r'明天|后天',q) and re.search(r'天气|下雨',recent):
        combined=q if re.search(r'天气|气温|下雨|weather|forecast',q,re.I) else recent
        city=next((city for city,alias in CITY_ALIASES.items() if city in combined or alias.lower() in combined.lower()),None)
        if not city:return None,'想查询哪个城市的天气？例如：南京今天、杭州明天。'
        offset=2 if '后天' in q else 1 if '明天' in q else 0
        days=3 if '三天' in q or '3天' in q else 1
        return ('get_weather',{'location':city,'days':days,'day_offset':offset}),None
    if re.search(r'新闻|资讯|news',q,re.I):
        category=next((c for c in ('国际','财经','健康','体育') if c in q),'健康' if re.search(r'医药|医疗|药企',q) else '综合')
        topic=re.sub(r'请|帮我|查询|查一下|搜索|最近|最新|今天|今日|有什么|有哪些|新闻|资讯|消息|热点|看看|的|[？?。！!\s]','',q)
        if topic in ('综合','国内','国际','财经','健康','体育','头条','科技','医药','医疗','药企'):topic=''
        return ('search_news',{'topic':topic[:80],'category':category,'limit':5,'since_days':1}),None
    return None,'当前已接入城市天气和新闻标题查询。请说明要查的城市、日期或新闻主题；其他实时服务暂未接入。'

def execute(name,args):
    if name=='get_weather' and set(args)=={'location','days','day_offset'}:return get_weather(**args)
    if name=='search_news' and set(args)=={'topic','category','limit','since_days'}:return search_news(**args)
    raise ValueError('联网工具名称或参数无效。')

def number(value,suffix=''):return '未提供' if value is None else str(value)+suffix
def render_live(name,data):
    if name=='get_weather':
        if data.get('needs_location'):return data['message']+('\n\n'+'；'.join(data.get('candidates',[])) if data.get('candidates') else '')
        current=data['current']
        lines=[f"{data['location']}（{data['region']}，{data['country']}）天气，时区 {data['timezone']}。",
            f"当前模型时间 {current['time']}：{current['description']}，{number(current['temperature_c'],'℃')}；体感 {number(current['feels_like_c'],'℃')}，风速 {number(current['wind_kmh'],' km/h')}。"]
        for day in data['forecast']:
            lines.append(f"{day['date']}：{day['description']}，{number(day['temperature_min_c'])}–{number(day['temperature_max_c'])}℃，当天最高降雨概率 {number(day['precipitation_probability_max_pct'],'%')}。")
        lines.extend([f"查询时间：{data['queried_at']}；数据来源：[Open-Meteo]({data['source_url']})。",data['note']])
        return '\n\n'.join(lines)
    lines=[f"中国新闻网近期新闻标题（过去{data['since_days']}天，类别：{data['category']}）。"]
    if not data['articles']:lines.append('已查询订阅源，但没有找到符合主题和时间范围的标题。可以扩大时间或换关键词；这不代表全网没有相关报道。')
    for index,item in enumerate(data['articles'],1):
        title=item['title'].replace('[','［').replace(']','］')
        url=item['url'].replace('(','%28').replace(')','%29')
        lines.append(f"{index}. [{title}]({url})\n发布时间：{item['published_at']}；来源：{item['publisher']}。")
    lines.extend([f"查询时间：{data['queried_at']}。",data['note']])
    if data.get('partial_failures'):lines.append('部分订阅源暂时不可用，以上结果来自成功查询的订阅。')
    return '\n\n'.join(lines)
