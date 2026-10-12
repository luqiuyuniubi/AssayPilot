"""Optional CDP browser acceptance: activation XLSX and arbitrary header mapping."""
import io,json,os,socket,subprocess,sys,time
from pathlib import Path
import requests,websocket
from docx import Document
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'pharma_agent'))
from local_access import load_access
if __name__=='__main__':
    output=ROOT/'.checks'/'flexible-browser';output.mkdir(parents=True,exist_ok=True)
    if (ROOT/'pharma_agent'/'.local'/'model.json').exists():raise RuntimeError('Use a fresh local checkout without saved model credentials.')
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    env=dict(os.environ,PHARMA_PORT=str(port),PYTHONUTF8='1')
    for k in ('PHARMA_LLM_API_KEY','PHARMA_LLM_BASE_URL','PHARMA_LLM_MODEL','PHARMA_SEARCH_API_KEY'):env.pop(k,None)
    with (output/'service.log').open('wb') as log:process=subprocess.Popen([sys.executable,'-B',str(ROOT/'pharma_agent'/'server.py')],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    base='http://127.0.0.1:'+str(port);session=requests.Session();session.trust_env=False
    browser=None;ws=None;tab=None;seq=0;events=[]
    cdp='http://127.0.0.1:9229'
    def call(method,params=None):
        global seq
        seq+=1;ws.send(json.dumps({'id':seq,'method':method,'params':params or {}}))
        while True:
            response=json.loads(ws.recv())
            if response.get('id')==seq:
                if response.get('error'):raise RuntimeError('Browser command failed.')
                return response.get('result',{})
            events.append(response)
    def js(expr):
        r=call('Runtime.evaluate',{'expression':expr,'returnByValue':True,'awaitPromise':True})
        if r.get('exceptionDetails'):raise RuntimeError('Browser JS exception: '+str(r['exceptionDetails'].get('text')))
        return r.get('result',{}).get('value')
    def wait(expr):
        for _ in range(200):
            if js(expr):return
            time.sleep(.1)
        raise RuntimeError('UI condition timed out: '+expr)
    def upload(selector,filename):
        doc=call('DOM.getDocument')['root']['nodeId'];node=call('DOM.querySelector',{'nodeId':doc,'selector':selector})['nodeId']
        call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(ROOT/'data'/'flexible'/filename)]})
    def select(id,value):js(f'$({json.dumps(id)}).value={json.dumps(value)};$({json.dumps(id)}).dispatchEvent(new Event("change"))')
    def analyze():
        old=js('currentJob');js('$("inspect").click()');wait('!$("settings").classList.contains("hidden")')
        js('$("confirm").click();$("analyze").click()');wait('currentJob!=='+json.dumps(old)+' && current!==null && current.id===currentJob && current.status==="completed"')
    try:
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('Child service stopped.')
            try:
                if session.get(base+'/api/health',timeout=.3).ok:
                    token=load_access(port,'2.0.0-flexible-assays')
                    if token:break
            except requests.RequestException:pass
            time.sleep(.1)
        else:raise RuntimeError('Child service timeout.')
        # Launch an isolated headless browser if there is no existing CDP port.
        try:session.get(cdp+'/json/version',timeout=.5).raise_for_status()
        except requests.RequestException:
            binary=next((p for p in [Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe',Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe'] if p.exists()),None)
            if binary is None:raise RuntimeError('Install Chrome/Edge for optional browser regression.')
            with socket.socket() as p:p.bind(('127.0.0.1',0));cdp_port=p.getsockname()[1]
            cdp='http://127.0.0.1:'+str(cdp_port)
            browser=subprocess.Popen([str(binary),'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-address=127.0.0.1','--remote-debugging-port='+str(cdp_port),'--remote-allow-origins='+cdp,'--user-data-dir='+str(output/('profile-'+str(time.time_ns()))),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            for _ in range(100):
                try:
                    if session.get(cdp+'/json/version',timeout=.3).ok:break
                except requests.RequestException:pass
                time.sleep(.1)
            else:raise RuntimeError('Headless browser did not start.')
        tab=session.put(cdp+'/json/new?about:blank',timeout=5).json()
        ws=websocket.create_connection(tab['webSocketDebuggerUrl'],timeout=20)
        call('Page.enable');call('Runtime.enable');call('Log.enable')
        call('Emulation.setDeviceMetricsOverride',{'width':1560,'height':1080,'deviceScaleFactor':1,'mobile':False})
        call('Page.navigate',{'url':base+'#access='+token});wait('typeof modelConfig!=="undefined" && modelConfig!==null')
        assert js('!modelConfig.enabled')
        select('assayType','activation');select('readout','RFU');upload('.rawfile','activation.xlsx');analyze()
        assert js('$("sampleTable").closest("table").innerText.includes("EC50") && current.result.results[0].samples[0].ic50_nm===null && Math.abs(endpoint(current.result.results[0].samples[0])-5)<.03')
        assert js('!$("chart").innerHTML.includes("NaN") && !$("chart").innerHTML.includes("Infinity")')
        js('document.querySelector("[data-tab=report]").click()');assert js('$("summary").value.includes("相对EC50")')
        exports=session.get(base+'/api/export',params={'id':js('currentJob'),'format':'docx'},headers={'X-AssayPilot-Token':token},timeout=20)
        exports.raise_for_status();doc=Document(io.BytesIO(exports.content));assert any('EC50' in c.text for t in doc.tables for row in t.rows for c in row.cells)
        js('$("batches").innerHTML="";demo=false;addBatch()');select('assayType','inhibition');upload('.rawfile','custom-headers.xlsx')
        js('document.querySelector(".probe").click()');wait('document.querySelector(".mapping [data-field=sample]")!==null')
        mapping={'sample':'compound_code','concentration':'dose_level','unit':'dose_units','value':'sensor_reading','role':'group_type'}
        for field,column in mapping.items():
            expr='document.querySelector('+json.dumps('.mapping [data-field='+field+']')+')'
            js(expr+'.value='+json.dumps(column)+';'+expr+'.dispatchEvent(new Event("change"))')
        analyze();assert js('Math.abs(endpoint(current.result.results[0].samples[0])-5)<.03 && current.result.results[0].provenance.import.mapping.value==="sensor_reading"')
        for example,expected in [('viability','CC50'),('enzyme','IC50'),('plate384','IC50'),('','IC50')]:
            select('exampleKind',example)
            js('$("demo").click()');wait('!$("settings").classList.contains("hidden")')
            old=js('currentJob');js('$("confirm").click();$("analyze").click()')
            wait('currentJob!=='+json.dumps(old)+' && current!==null && current.id===currentJob && current.status==="completed"')
            assert js('current.result.results[0].assay.potency_label==='+json.dumps(expected)+' && !$("chart").innerHTML.includes("NaN")')
        images=ROOT/'docs'/'screenshots';images.mkdir(exist_ok=True)
        js('document.querySelector("[data-tab=overview]").click()');
        import base64
        box=js('(()=>{let r=$("results").getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}})()')
        (images/'flexible-analysis.png').write_bytes(base64.b64decode(call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True,'clip':box})['data']))
        call('Page.reload',{'ignoreCache':True});wait('typeof modelConfig!=="undefined" && modelConfig!==null')
        errors=[e for e in events if e.get('method')=='Runtime.exceptionThrown' or e.get('method')=='Log.entryAdded' and e.get('params',{}).get('entry',{}).get('source')=='security' and e.get('params',{}).get('entry',{}).get('level')=='error']
        if errors:raise RuntimeError('Application script or CSP errors occurred.')
        evidence={'version':'2.0.0-flexible-assays','real_xlsx_upload_ec50':True,'custom_header_ui_mapping':True,'single_file_record_optional':True,'report_ec50':True,'viability_cc50':True,'enzyme_ic50':True,'plate384_demo':True,'legacy96_demo':True,'no_nan_chart':True,'refresh_auth':True,'browser_errors':0,'paid_calls':False}
        (ROOT/'.checks'/'flexible-browser.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(evidence))
    finally:
        if ws:ws.close()
        if tab:session.get(cdp+'/json/close/'+tab['id'],timeout=5)
        if browser and browser.poll() is None:browser.terminate();browser.wait(timeout=10)
        process.terminate();process.wait(timeout=10)
        p=ROOT/'pharma_agent'/'.local'/('access-'+str(port)+'.json')
        if p.exists():p.unlink()
