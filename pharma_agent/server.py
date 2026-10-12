import base64,io,json,os,sys,threading,time,uuid,zipfile,socket,hashlib,re
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from datasets import preview as inspect
from imports import EXTENSIONS,describe
from assays import PROFILES
from agent import run_workflow,interpret,config,test_connection
from model_settings import save as save_model_settings
from reports import make_docx,make_brief_docx,make_html,chart_png
from web_settings import public as web_config,save as save_web_settings
from web_tools import web_search
from local_access import validate_headers,save_access,remove_access,API_SLOTS,rate_allow

ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parent
JOBS={}; CHAT_SESSIONS={}; LOCK=threading.Lock()
MAX_BODY=24*1024*1024
VERSION="2.0.0-flexible-assays"

def html_policy(data):
    # HTML parsers normalize CRLF and CR before the browser hashes inline script
    # text. Use those same bytes so Windows checkouts do not block our own UI.
    normalized=data.replace(b'\r\n',b'\n').replace(b'\r',b'\n')
    hashes=["'sha256-"+base64.b64encode(hashlib.sha256(script).digest()).decode()+"'" for script in re.findall(rb'<script>(.*?)</script>',normalized,re.S)]
    return "default-src 'self'; script-src "+(' '.join(hashes) or "'none'")+"; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'"
def sample_batches(example=None):
    data=WORKSPACE/"data"
    examples={'inhibition':'inhibition.csv','activation':'activation.xlsx','viability':'viability.json','enzyme':'enzyme.json','custom':'custom-headers.xlsx','plate384':'matrix-384.xlsx'}
    if example:
        if example not in examples:raise ValueError('示例不存在。')
        raw=data/'flexible'/examples[example];record=data/'flexible'/'design-384.tsv' if example=='plate384' else None
        config={'raw':{'columns':dict(zip(('sample','concentration','unit','value','role'),('compound_code','dose_level','dose_units','sensor_reading','group_type'))),'sheet':'Measurements','header_row':2}} if example=='custom' else {}
        return [{'name':'合成'+example+'演示','raw':raw.read_bytes(),'raw_name':raw.name,'record':record.read_bytes() if record else None,'record_name':record.name if record else '', 'import_config':config}]
    raw=data/"RAW DATA.csv";record=data/"record.xlsx"
    if not raw.exists() or not record.exists():raise ValueError("未找到合成示例；请在仓库根目录运行 python tools/generate_sample.py。")
    return [{"name":"合成演示数据（非真实实验）","raw":raw.read_bytes(),"record":record.read_bytes(),"raw_name":raw.name,"record_name":record.name}]

def decode_batches(body):
    if body.get("demo") is True:return sample_batches(body.get('example'))
    arr=body.get("batches",[])
    if not 1<=len(arr)<=5:raise ValueError("请添加1–5个批次，每批包含CSV和XLSX。")
    out=[]
    for i,b in enumerate(arr):
        item={"name":str(b.get("name",f"批次{i+1}"))[:100],"import_config":b.get('import_config',{})}
        if not isinstance(item['import_config'],dict):raise ValueError('导入映射必须为对象。')
        for field in ('raw','record'):
            filename=Path(str(b.get(field+"_name",""))).name
            if field=='record' and not b.get(field):item[field]=None;item[field+'_name']='';continue
            if Path(filename).suffix.lower() not in EXTENSIONS:raise ValueError("输入支持CSV、TSV、TXT、XLSX、JSON数值表。")
            data=base64.b64decode(b.get(field,""),validate=True)
            if not data or len(data)>8*1024*1024:raise ValueError("每个文件需为非空且不超过8MB。")
            item[field]=data;item[field+"_name"]=filename
        out.append(item)
    return out
def worker(jobid,batches,options):
    def progress(stage,trace):
        with LOCK:JOBS[jobid].update(stage=stage,trace=list(trace))
    try:
        result=run_workflow(batches,options,progress)
        with LOCK:JOBS[jobid].update(status="completed",stage="完成",result=result,trace=result["trace"])
    except Exception as e:
        with LOCK:JOBS[jobid].update(status="failed",stage="失败",error=str(e))

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def setup(self):
        super().setup();self.connection.settimeout(20)
    def guard(self,api=False):
        failure=validate_headers(self.headers,self.server.server_port,api)
        if failure:self.respond({'error':failure[1]},status=failure[0]);return False
        return True
    def source_key(self):return self.client_address[0] if self.client_address else 'unknown'
    def respond(self,data,ctype="application/json; charset=utf-8",status=200,filename=None):
        if isinstance(data,(dict,list)):data=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
        if isinstance(data,str):data=data.encode()
        self.send_response(status);self.send_header("Content-Type",ctype);self.send_header("Content-Length",str(len(data)));self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff");self.send_header("X-Frame-Options","DENY");self.send_header("Referrer-Policy","no-referrer");self.send_header("Permissions-Policy","camera=(), microphone=(), geolocation=()");self.send_header("Cross-Origin-Resource-Policy","same-origin")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy",html_policy(data))
        if filename:self.send_header("Content-Disposition",f'attachment; filename="{filename}"')
        self.end_headers();self.wfile.write(data)
    def read_body(self):
        if self.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':raise ValueError('接口只接受JSON请求。')
        if self.headers.get('Transfer-Encoding'):raise ValueError('不接受分块请求。')
        length=int(self.headers.get("Content-Length",0))
        if not 0<length<=MAX_BODY:raise ValueError("请求体为空或超过24MB。")
        body=json.loads(self.rfile.read(length))
        if not isinstance(body,dict):raise ValueError('请求必须为JSON对象。')
        return body
    def do_GET(self):
        try:
            u=urlparse(self.path);q=parse_qs(u.query)
            if not self.guard(api=u.path.startswith('/api/') and u.path!='/api/health'):return
            if u.path=='/api/health':return self.respond({'version':VERSION,'local_only':True,'auth_required':True})
            if u.path.startswith('/api/') and not rate_allow(self.source_key()+'|GET',120):return self.respond({'error':'请求过于频繁，请稍后重试。'},status=429)
            if u.path=="/":return self.respond((ROOT/"web"/"index.html").read_bytes(),"text/html; charset=utf-8")
            if u.path=="/api/config":return self.respond({**config(),"version":VERSION,"report_format":"generic","web":web_config()})
            if u.path=="/api/web-config":return self.respond(web_config())
            if u.path=="/api/formats":return self.respond({'extensions':sorted(EXTENSIONS),'assays':PROFILES})
            if u.path=="/api/jobs":
                return self.respond([{"id":k,"status":v["status"],"stage":v["stage"],"created":v["created"]} for k,v in list(JOBS.items())[-20:]][::-1])
            if u.path.startswith("/api/jobs/"):
                id=u.path.split("/")[-1];job=JOBS.get(id)
                if job is None:return self.respond({"error":"任务不存在，服务重启后历史会话已清空。"},status=404)
                with LOCK: snapshot=dict(job)
                return self.respond(snapshot)
            if u.path=="/api/export":
                id=q.get("id",[""])[0];job=JOBS.get(id)
                if not job or job["status"]!="completed":raise ValueError("分析尚未完成。")
                result=job["result"];fmt=q.get("format",["docx"])[0];index=int(q.get("batch",["0"])[0]);edited=job.get("edited",{}).get(str(index))
                if not 0<=index<len(result["results"]):raise ValueError("批次不存在。")
                if fmt=="docx":return self.respond(make_docx(result,index,edited),"application/vnd.openxmlformats-officedocument.wordprocessingml.document",filename="assay-report.docx")
                if fmt=="brief":return self.respond(make_brief_docx(result,index,edited),"application/vnd.openxmlformats-officedocument.wordprocessingml.document",filename="assay-report-brief.docx")
                if fmt=="html":return self.respond(make_html(result,index,edited),"text/html; charset=utf-8",filename="assay-report.html")
                if fmt=="png":return self.respond(chart_png([result["results"][index]]),"image/png",filename="dose-response.png")
                if fmt=="json":return self.respond({"analysis":result,"manual_edits":job.get("edited",{}),"chat":job.get("chat",[])},"application/json; charset=utf-8",filename="audit.json")
                if fmt=="zip":
                    out=io.BytesIO()
                    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
                        for i,r in enumerate(result["results"]):
                            z.writestr(f"batch-{i+1}-report.docx",make_docx(result,i,job.get("edited",{}).get(str(i))))
                            z.writestr(f"batch-{i+1}-report-brief.docx",make_brief_docx(result,i,job.get("edited",{}).get(str(i))))
                            z.writestr(f"batch-{i+1}-report.html",make_html(result,i,job.get("edited",{}).get(str(i))))
                            z.writestr(f"batch-{i+1}-curve.png",chart_png([r]))
                        z.writestr("audit.json",json.dumps({"analysis":result,"manual_edits":job.get("edited",{}),"chat":job.get("chat",[])},ensure_ascii=False,indent=2))
                    return self.respond(out.getvalue(),"application/zip",filename="assay-deliverables.zip")
            self.respond({"error":"页面不存在"},status=404)
        except Exception as e:self.respond({"error":str(e)},status=400)
    def do_POST(self):
        if not self.guard(api=True):return
        if not rate_allow(self.source_key()+'|POST',30):return self.respond({'error':'请求过于频繁，请稍后重试。'},status=429)
        if urlparse(self.path).path=='/api/chat' and not rate_allow(self.source_key()+'|CHAT',12):return self.respond({'error':'聊天请求过于频繁，请稍后再试。'},status=429)
        if not API_SLOTS.acquire(blocking=False):return self.respond({'error':'已有较多请求处理中，请稍后重试。'},status=429)
        try:
            body=self.read_body();path=urlparse(self.path).path
            if path=="/api/config":return self.respond(save_model_settings(body))
            if path=="/api/web-config":return self.respond(save_web_settings(body))
            if path=="/api/web-test":
                result=web_search('Open-Meteo天气API',3,'any')
                return self.respond({'ok':bool(result['results']),'message':result['provider']+'已返回'+str(len(result['results']))+'条结果；质量和新鲜度需核对。'})
            if path=="/api/model-test":return self.respond(test_connection())
            if path=="/api/probe":
                batches=decode_batches(body)
                return self.respond({'batches':[{'name':b['name'],'raw':describe(b['raw'],b['raw_name']),'record':describe(b['record'],b['record_name']) if b['record'] else None} for b in batches]})
            if path=="/api/inspect":
                batches=decode_batches(body)
                return self.respond({"batches":[{"name":b["name"],**inspect(b["raw"],b.get("record"),b['raw_name'],b.get('record_name',''),b.get('import_config'),body.get('options',{}))} for b in batches]})
            if path=="/api/analyze":
                if not body.get("confirmed"):raise ValueError("请先核对并确认实验设计。")
                batches=decode_batches(body);options=body.get("options",{})
                if not isinstance(options,dict):raise ValueError("配置格式错误")
                with LOCK:
                    if sum(j["status"]=="running" for j in JOBS.values())>=2:raise ValueError("已有两个任务处理中，请稍后重试。")
                    if len(JOBS)>40:
                        for old in list(JOBS):
                            if JOBS[old]["status"]!="running":del JOBS[old];break
                    id=uuid.uuid4().hex
                    JOBS[id]={"id":id,"status":"running","stage":"准备","trace":[],"created":time.strftime("%Y-%m-%d %H:%M:%S"),"chat":[]}
                threading.Thread(target=worker,args=(id,batches,options),daemon=True).start()
                return self.respond({"id":id})
            if path=="/api/edit":
                id=body.get("id");job=JOBS.get(id)
                if not job or job["status"]!="completed":raise ValueError("请先完成分析。")
                if path=="/api/edit":
                    index=str(int(body.get("batch",0)))
                    if int(index)>=len(job["result"]["results"]) or int(index)<0:raise ValueError("批次不存在")
                    text=str(body.get("summary","")).strip()
                    if not text or len(text)>5000:raise ValueError("摘要需为1–5000字符。")
                    with LOCK:job.setdefault("edited",{})[index]=text
                    return self.respond({"saved":True})
            if path=="/api/chat":
                id=body.get("id");job=JOBS.get(id)
                if id and (not job or job["status"]!="completed"):raise ValueError("请先完成该实验分析，或不选择实验任务直接聊天。")
                question=str(body.get("question","")).strip()
                if not question or len(question)>5000:raise ValueError("请输入1–5000字符的问题。")
                session_id=None
                if job:
                    conversation=job;results=job["result"]["results"]
                else:
                    with LOCK:
                        session_id=body.get("session")
                        if not isinstance(session_id,str) or session_id not in CHAT_SESSIONS:
                            session_id=uuid.uuid4().hex
                            if len(CHAT_SESSIONS)>=60:CHAT_SESSIONS.pop(next(iter(CHAT_SESSIONS)))
                            CHAT_SESSIONS[session_id]={"chat":[],"trace":[]}
                        conversation=CHAT_SESSIONS[session_id]
                    results=[]
                trace=[];answer,mode,error=interpret(results,question,trace,conversation.get("chat",[]))
                intent=next((t.get("intent") for t in trace if t.get("step")=="范围判断"),None)
                with LOCK:
                    conversation["chat"].extend([{"role":"user","content":question,"intent":intent},{"role":"assistant","content":answer,"intent":intent,"mode":mode,"error":error}])
                    conversation["chat"]=conversation["chat"][-40:]
                    if job:job["result"]["trace"].extend(trace)
                    else:conversation["trace"].extend(trace);conversation["trace"]=conversation["trace"][-100:]
                return self.respond({"answer":answer,"mode":mode,"error":error,"trace":trace,"intent":intent,"session":session_id})
            self.respond({"error":"接口不存在"},status=404)
        except Exception as e:self.respond({"error":str(e)},status=400)
        finally:API_SLOTS.release()
def serve(port=None):
    port=port or int(os.environ.get("PHARMA_PORT","8765"))
    class LocalServer(ThreadingHTTPServer):
        allow_reuse_address=False
        def server_bind(self):
            if os.name=="nt":self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            super().server_bind()
    server=LocalServer(("127.0.0.1",port),Handler)
    save_access(port,VERSION)
    print(f"Pharma Agent: http://127.0.0.1:{port}",flush=True)
    try:server.serve_forever()
    finally:server.server_close();remove_access(port)

if __name__=="__main__":serve()
