"""Provider adapters. API responses are normalized for the existing tool loop."""
import json,urllib.request,urllib.error

class ModelServiceError(RuntimeError):
    def __init__(self,message,code):
        super().__init__(message)
        self.code=code

class NoCredentialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ModelServiceError('模型接口发生重定向，已阻止密钥转发。请核对服务地址。','redirect_blocked')

def open_model_request(request,timeout):
    return urllib.request.build_opener(NoCredentialRedirect()).open(request,timeout=timeout)

def responses_input(messages):
    items=[]
    for m in messages:
        if m.get("_response_output") is not None:
            # Carry opaque reasoning and function-call items back unchanged.
            items.extend(m["_response_output"])
        elif m["role"]=="tool":
            items.append({"type":"function_call_output","call_id":m["tool_call_id"],"output":m["content"]})
        elif m.get("tool_calls"):
            if m.get("content"):items.append({"role":"assistant","content":m["content"]})
            for call in m["tool_calls"]:
                items.append({"type":"function_call","call_id":call["id"],"name":call["function"]["name"],"arguments":call["function"]["arguments"]})
        else:
            items.append({"role":m["role"],"content":m.get("content") or ""})
    return items

def build_request(cfg,messages,tools=None,tool_choice=None):
    provider=cfg["provider"]
    base=cfg["base_url"].rstrip("/")
    headers={"Content-Type":"application/json","Authorization":"Bearer "+cfg["api_key"]}
    if provider=="openai":
        payload={"model":cfg["model"],"input":responses_input(messages),"max_output_tokens":4096,
                 "store":False,"include":["reasoning.encrypted_content"]}
        if tools:
            payload["tools"]=[{"type":"function",**t["function"],"parameters":{**t["function"]["parameters"],"required":t["function"]["parameters"].get("required",[])},"strict":True} for t in tools]
            if isinstance(tool_choice,dict):
                payload["tool_choice"]={"type":"function","name":tool_choice["function"]["name"]}
            else:payload["tool_choice"]=tool_choice or "auto"
        return base+"/responses",headers,payload,"responses"
    # Compatible endpoints require complete tool messages, including Gemini's
    # extra_content/thought signatures and opaque nested tool-call fields.
    chat=[]
    for m in messages:
        clean={k:v for k,v in m.items() if k in ("role","content","tool_calls","tool_call_id","name","reasoning_content","reasoning_details","extra_content")}
        chat.append(clean)
    payload={"model":cfg["model"],"messages":chat,"max_tokens":4096,"stream":False}
    if provider!="gemini":payload["temperature"]=0.1
    if tools:
        payload["tools"]=tools;payload["tool_choice"]=tool_choice or "auto"
        if provider=="mistral" and isinstance(tool_choice,dict):
            # Mistral documents 'any' to force tool use; expose only the one
            # required function so the first evidence lookup remains forced.
            name=tool_choice["function"]["name"]
            payload["tools"]=[t for t in tools if t["function"]["name"]==name]
            payload["tool_choice"]="any";payload["parallel_tool_calls"]=False
        if provider=="openrouter":
            payload["provider"]={"require_parameters":True}
    if provider=="deepseek":payload["thinking"]={"type":"disabled"}
    if provider=="qwen":payload["enable_thinking"]=False
    if provider=="groq" and cfg["model"].startswith("openai/gpt-oss-"):payload["reasoning_effort"]="low"
    return base+"/chat/completions",headers,payload,"chat"

def normalize(data,protocol):
    if protocol=="responses":
        if data.get("status") in ("incomplete","failed"):
            raise RuntimeError("模型回答未完成；请重试或换用较快模型。")
        output=data["output"]
        text=[];calls=[]
        for item in output:
            if item.get("type")=="message":
                text.extend(block["text"] for block in item.get("content",[]) if block.get("type")=="output_text")
            elif item.get("type")=="function_call":
                calls.append({"id":item["call_id"],"type":"function","function":{"name":item["name"],"arguments":item["arguments"]}})
        message={"role":"assistant","content":"\n".join(text) or None,"_response_output":output}
        if calls:message["tool_calls"]=calls
        return message
    choice=data["choices"][0]
    if choice.get("finish_reason")=="length":
        raise RuntimeError("模型回答达到输出限制，未完整返回；请缩短提问或换用模型。")
    return choice["message"]

def send(cfg,messages,tools=None,tool_choice=None):
    url,headers,payload,protocol=build_request(cfg,messages,tools,tool_choice)
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers=headers)
    try:
        with open_model_request(req,timeout=45) as res:
            raw=res.read(2*1024*1024+1)
            if len(raw)>2*1024*1024:raise ModelServiceError('模型响应过大，已停止读取。','response_too_large')
            return normalize(json.loads(raw),protocol)
    except urllib.error.HTTPError as e:
        reasons={401:"API Key无效或与服务不匹配",403:"账户权限或服务区域不可用",
                 404:"服务地址或模型名称不存在",429:"调用额度不足或请求过于频繁"}
        raise ModelServiceError(f"模型服务返回HTTP {e.code}："+reasons.get(e.code,"请检查账户、模型和接口配置"),"http_"+str(e.code)) from None
    except (urllib.error.URLError,TimeoutError) as e:
        reason=getattr(e,"reason",e)
        error_number=getattr(reason,"winerror",None) or getattr(reason,"errno",None)
        if isinstance(reason,ConnectionRefusedError) or error_number in (61,111,10061):
            raise ModelServiceError("模型连接被拒绝，可能是当前运行环境限制网络或代理不可达。请在允许联网的本机环境启动服务，并检查代理设置。","connection_refused") from None
        if isinstance(reason,PermissionError) or error_number in (13,10013):
            raise ModelServiceError("当前运行环境禁止模型网络连接，请在允许联网的本机环境启动服务。","network_denied") from None
        if isinstance(reason,TimeoutError):
            raise ModelServiceError("模型服务连接超时，请检查网络或稍后重试。","timeout") from None
        raise ModelServiceError("模型服务连接失败，请检查网络、代理与服务地址。","connection_failed") from None
    except (KeyError,IndexError,TypeError,json.JSONDecodeError):
        raise RuntimeError("模型服务返回格式不兼容。") from None

def assistant_history(message):
    return {k:message[k] for k in ("role","content","tool_calls","reasoning_content","reasoning_details","extra_content","_response_output") if k in message}
