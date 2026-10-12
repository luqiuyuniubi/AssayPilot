"""Local runtime configuration. Optional Windows DPAPI persistence; no key in public responses."""
import os, json, threading, base64, ctypes
from pathlib import Path
from urllib.parse import urlparse
PRESETS={
 "deepseek":{"label":"DeepSeek 官方","base_url":"https://api.deepseek.com","model":"deepseek-flash"},
 "qwen":{"label":"通义千问 · 百炼北京","base_url":"https://dashscope.aliyuncs.com/compatible-mode/v1","model":"qwen-plus"},
 "openai":{"label":"OpenAI 官方","base_url":"https://api.openai.com/v1","model":"gpt-4.1-mini"},
 "gemini":{"label":"Google Gemini","base_url":"https://generativelanguage.googleapis.com/v1beta/openai","model":"gemini-3.8-flash"},
 "mistral":{"label":"Mistral AI","base_url":"https://api.mistral.ai/v1","model":"mistral-small-latest"},
 "groq":{"label":"Groq（高速）","base_url":"https://api.groq.com/openai/v1","model":"openai/gpt-oss-120b"},
 "openrouter":{"label":"OpenRouter（可选 Claude / GPT / Gemini）","base_url":"https://openrouter.ai/api/v1","model":"openai/gpt-oss-120b"},
 "custom":{"label":"自定义兼容接口","base_url":"","model":""},
}
PROVIDER_HELP={
 "deepseek":"使用 DeepSeek 开放平台的 API Key。",
 "qwen":"使用百炼北京地域的 API Key，可填写北京业务空间专属地址。",
 "openai":"使用 OpenAI API 平台的 API Key；ChatGPT 订阅与 API 额度分开。",
 "gemini":"使用 Google AI Studio 的 Gemini API Key。",
 "mistral":"使用 Mistral 控制台的 API Key。",
 "groq":"使用 GroqCloud 的 API Key，模型名以账户可用列表为准。",
 "openrouter":"使用 OpenRouter 的 API Key；填写其模型目录中的完整名称，例如服务商/模型名。",
 "custom":"用于公司网关或本地服务；填写支持工具调用的兼容接口。",
}
for name,preset in PRESETS.items():
    preset["group"]="自定义" if name=="custom" else "国内服务" if name in ("deepseek","qwen") else "国外服务"
    preset["help"]=PROVIDER_HELP[name]
PRESETS["openai"]["models"]=["gpt-4.1-mini","gpt-4.1","gpt-5.4-mini","gpt-5.4"]
PRESETS["mistral"]["models"]=["mistral-small-latest","mistral-medium-latest","mistral-large-latest"]
PRESETS["groq"]["models"]=["openai/gpt-oss-120b","openai/gpt-oss-20b"]
PRESETS["openrouter"]["models"]=["openai/gpt-oss-120b","anthropic/claude-sonnet-4.6"]
PRESETS["deepseek"]["models"]=["deepseek-flash","deepseek-v4-pro"]
PRESETS["qwen"]["models"]=["qwen-plus","qwen-max","qwen-flash","qwen3.7-plus","qwen3.7-flash"]
PRESETS["gemini"]["models"]=["gemini-3.8-flash","gemini-3.7-flash","gemini-3.6-flash","gemini-2.5-flash","gemini-2.5-pro","gemini-2.5-flash-lite"]
PRESETS["groq"]["models"] += ["llama-3.3-70b-versatile"]
PRESETS["openrouter"]["models"] += ["google/gemini-2.5-flash"]
PATH=Path(__file__).resolve().parent/".local"/"model.json"
LOCK=threading.Lock()
RUNTIME=None
class Blob(ctypes.Structure):
    _fields_=[("size",ctypes.c_ulong),("data",ctypes.POINTER(ctypes.c_byte))]
def protect(data,decrypt=False):
    if os.name!="nt":raise ValueError("加密保存密钥仅支持Windows；请使用仅本次会话配置。")
    buf=ctypes.create_string_buffer(data);inp=Blob(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_byte)));out=Blob()
    crypt=ctypes.windll.crypt32
    if decrypt:ok=crypt.CryptUnprotectData(ctypes.byref(inp),None,None,None,None,1,ctypes.byref(out))
    else:ok=crypt.CryptProtectData(ctypes.byref(inp),"AssayPilot model key",None,None,None,1,ctypes.byref(out))
    if not ok:raise ValueError("Windows密钥加密/解密失败；请重新配置。")
    try:return ctypes.string_at(out.data,out.size)
    finally:
        kernel=ctypes.windll.kernel32
        kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree(ctypes.cast(out.data,ctypes.c_void_p))
def load_saved():
    if not PATH.exists():return None
    try:
        d=json.loads(PATH.read_text(encoding="utf-8"))
        d["api_key"]=protect(base64.b64decode(d.pop("encrypted_key")),True).decode()
        return d
    except Exception:return None
RUNTIME=load_saved()
def effective():
    with LOCK:
        if RUNTIME is not None:return dict(RUNTIME)
    return {"enabled":bool(os.environ.get("PHARMA_LLM_API_KEY")),"provider":"custom","base_url":os.environ.get("PHARMA_LLM_BASE_URL",""),"model":os.environ.get("PHARMA_LLM_MODEL",""),"api_key":os.environ.get("PHARMA_LLM_API_KEY",""),"remember":False}
def validate(c):
    if c.get("provider") not in PRESETS:raise ValueError("请选择有效模型服务。")
    if c.get("enabled"):
        u=urlparse(c.get("base_url",""))
        if u.scheme!="https" and not (u.scheme=="http" and u.hostname in ("127.0.0.1","localhost","::1")):raise ValueError("远程服务需使用HTTPS，本机服务可使用HTTP。")
        if not u.hostname or u.username or u.password or u.query or u.fragment:raise ValueError("Base URL格式错误，不能包含账号、参数或片段。")
        hosts={
            "deepseek":{"api.deepseek.com"},
            "qwen":{"dashscope.aliyuncs.com"},
            "openai":{"api.openai.com"},
            "gemini":{"generativelanguage.googleapis.com"},
            "mistral":{"api.mistral.ai"},
            "groq":{"api.groq.com"},
            "openrouter":{"openrouter.ai"},
        }
        if c["provider"]=="qwen" and not (u.hostname in hosts["qwen"] or u.hostname.endswith(".cn-beijing.maas.aliyuncs.com")):raise ValueError("百炼北京预设需使用北京地域官方域名。")
        if c["provider"] in hosts and c["provider"]!="qwen" and u.hostname not in hosts[c["provider"]]:raise ValueError("该模型预设只能使用对应官方域名。")
        if not c.get("model") or not c.get("api_key"):raise ValueError("启用模型需要模型名称和API Key。")
        if any(x in c["api_key"] for x in "\r\n"):raise ValueError("API Key格式错误。")
    return c
def save(body):
    global RUNTIME
    old=effective();p=str(body.get("provider","deepseek"))
    if p not in PRESETS:raise ValueError("模型服务不存在。")
    base=str(body.get("base_url",PRESETS[p]["base_url"])).strip().rstrip("/")
    key=str(body.get("api_key","")).strip()
    if not key and p==old.get("provider") and base==old.get("base_url","").rstrip("/"):key=old.get("api_key","")
    c={"provider":p,"enabled":bool(body.get("enabled")),"base_url":base,"model":str(body.get("model",PRESETS[p]["model"])).strip(),"api_key":key,"remember":bool(body.get("remember"))}
    validate(c)
    if c["remember"] and c["enabled"]:
        disk={k:v for k,v in c.items() if k!="api_key"}
        disk["encrypted_key"]=base64.b64encode(protect(key.encode())).decode()
        PATH.parent.mkdir(exist_ok=True);tmp=PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(disk,ensure_ascii=False),encoding="utf-8");tmp.replace(PATH)
    elif PATH.exists():PATH.unlink()
    with LOCK:RUNTIME=c
    return public()
def public():
    c=effective();enabled=c.get("enabled",False) and bool(c.get("api_key"))
    return {"enabled":enabled,"provider":c["provider"],"model":c["model"],"base_url":c["base_url"],"has_key":bool(c.get("api_key")),"remember":c.get("remember",False),"mode":"已配置大模型（连接状态请测试）" if enabled else "本地规则编排（未调用大模型）","presets":PRESETS}
