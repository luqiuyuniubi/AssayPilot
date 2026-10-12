"""Fresh child service, local synthetic upload, confirmation and export regression."""
import base64,io,json,os,socket,subprocess,sys,time,zipfile
from pathlib import Path
import urllib.request,urllib.error
from docx import Document
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pharma_agent'))
from local_access import load_access
def main():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    base='http://127.0.0.1:'+str(port)
    env=dict(os.environ,PHARMA_PORT=str(port),PYTHONUTF8='1',MPLCONFIGDIR=str(ROOT/'pharma_agent'/'.local'/'matplotlib'))
    for key in ('PHARMA_LLM_API_KEY','PHARMA_LLM_BASE_URL','PHARMA_LLM_MODEL','PHARMA_SEARCH_API_KEY'):env.pop(key,None)
    env['PHARMA_SEARCH_PROVIDER']='public'
    # An existing personal configuration must not cause test model calls.
    if (ROOT/'pharma_agent'/'.local'/'model.json').exists():raise RuntimeError('Run smoke test in a fresh checkout without saved model credentials.')
    checks=ROOT/'.checks';checks.mkdir(exist_ok=True)
    token='';opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path,body=None,authenticated=True):
        headers={'X-AssayPilot-Token':token} if authenticated else {}
        if body is not None:headers['Content-Type']='application/json'
        req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with opener.open(req,timeout=30) as r:return r.read(),r.headers
    def api(path,body=None):return json.loads(request(path,body)[0])
    with (checks/'http-smoke.log').open('wb') as log:
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        process=subprocess.Popen([sys.executable,'-B',str(ROOT/'pharma_agent'/'server.py')],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=flags)
    try:
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('Child service stopped; inspect .checks/http-smoke.log.')
            try:
                health=json.loads(request('/api/health',authenticated=False)[0]);token=load_access(port,health['version'])
                if token:break
            except (OSError,ValueError):pass
            time.sleep(.1)
        else:raise RuntimeError('Child service did not become ready.')
        try:request('/api/config',authenticated=False);raise AssertionError('Missing token accepted.')
        except urllib.error.HTTPError as e:assert e.code==401
        cfg=api('/api/config');assert cfg['version']=='2.0.0-flexible-assays' and not cfg['enabled']
        raw=(ROOT/'data'/'RAW DATA.csv').read_bytes();record=(ROOT/'data'/'record.xlsx').read_bytes()
        batch={'name':'合成HTTP验收','raw_name':'RAW DATA.csv','record_name':'record.xlsx','raw':base64.b64encode(raw).decode(),'record':base64.b64encode(record).decode()}
        body={'batches':[batch]};assert len(api('/api/inspect',body)['batches'][0]['samples'])==4
        try:api('/api/analyze',{**body,'confirmed':False});raise AssertionError('Confirmation bypass accepted.')
        except urllib.error.HTTPError as e:assert e.code==400
        job_id=api('/api/analyze',{**body,'confirmed':True})['id']
        for _ in range(100):
            job=api('/api/jobs/'+job_id)
            if job['status']!='running':break
            time.sleep(.1)
        assert job['status']=='completed',job.get('error')
        samples=job['result']['results'][0]['samples']
        for sample,expected in zip(samples,[3.2,7.5,18.0]):assert abs(sample['ic50_nm']-expected)<.03
        assert samples[3]['ic50_nm'] is None
        for fmt in ('docx','brief','html','png','json','zip'):
            content,_=request('/api/export?id='+job_id+'&format='+fmt)
            if fmt=='docx':assert len(Document(io.BytesIO(content)).sections[0].header.tables)==1
            if fmt=='zip':
                with zipfile.ZipFile(io.BytesIO(content)) as z:assert len(z.namelist())==5
        answer=api('/api/chat',{'id':job_id,'question':'Drug4为什么没有IC50？'});assert 'Drug4' in answer['answer']
        evidence={'version':cfg['version'],'fresh_service':True,'synthetic_upload':True,'confirmation_gate':True,'no_token_rejected':True,'analysis':True,'six_export_formats':True,'generic_header_table':True,'local_model_free_chat':True,'external_model_calls':False}
        (checks/'http-smoke.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(evidence))
    finally:
        process.terminate();process.wait(timeout=10)
        access=ROOT/'pharma_agent'/'.local'/('access-'+str(port)+'.json')
        if access.exists():access.unlink()
if __name__=='__main__':main()
