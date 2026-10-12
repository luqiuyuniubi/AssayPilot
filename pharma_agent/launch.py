"""Double-click entry: reuses local service and opens user-requested browser."""
import sys, importlib.util, urllib.request, json, webbrowser, threading, time, runpy, socket
from pathlib import Path
from local_access import load_access
missing=[name for name in ("numpy","scipy","openpyxl","docx","matplotlib","defusedxml") if not importlib.util.find_spec(name)]
if missing:
    print("首次使用请安装依赖：python -m pip install -r requirements.txt")
    print("缺失组件："+", ".join(missing))
    sys.exit(1)
import os
if os.name!="nt":raise SystemExit("当前启动器使用Windows DPAPI，请使用Windows运行；其他平台尚未支持完整启动流程。")
VERSION="2.0.0-flexible-assays"
def find_service():
    ports=[int(os.environ["PHARMA_PORT"])] if os.environ.get("PHARMA_PORT") else range(8765,8775)
    free=[];older=False
    for candidate in ports:
        address="http://127.0.0.1:"+str(candidate)
        try:
            with urllib.request.urlopen(address+"/api/health",timeout=.3) as r:cfg=json.load(r)
            if cfg.get("version")==VERSION:
                token=load_access(candidate,VERSION)
                if token:
                    request=urllib.request.Request(address+'/api/config',headers={'X-AssayPilot-Token':token})
                    with urllib.request.urlopen(request,timeout=.5) as response:json.load(response)
                    return candidate,True,older
                older=True;continue
            older=True
        except Exception:
            try:
                with socket.socket() as probe:probe.bind(("127.0.0.1",candidate))
                free.append(candidate)
            except OSError:pass
    if not free:raise RuntimeError("本地端口已占用，请关闭其他项目服务后再启动。")
    return free[0],False,older
port,reuse,older=find_service()
url="http://127.0.0.1:"+str(port)
def open_workspace():
    token=load_access(port,VERSION)
    if not token:return False
    webbrowser.open(url+'#access='+token);return True
if reuse:
    print("项目已运行："+url)
    if not open_workspace():raise RuntimeError('访问凭证不可用，请在服务运行账户下重新启动。')
    sys.exit(0)
if older:print("检测到旧版会话，保留原会话并启动新版。请在新版页面配置模型。")
os.environ["PHARMA_PORT"]=str(port)
def open_browser():
    for _ in range(30):
        try:
            with urllib.request.urlopen(url+"/api/health",timeout=1) as r:json.load(r)
            if open_workspace():return
        except Exception:time.sleep(.3)
threading.Thread(target=open_browser,daemon=True).start()
print("关闭本窗口会停止服务；所有结果请先导出。")
runpy.run_path(str(Path(__file__).resolve().parent/"server.py"),run_name="__main__")
