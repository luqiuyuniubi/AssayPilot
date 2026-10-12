"""Validate provider wire protocols and round trips, without real model credentials."""
import io,json,unittest,urllib.error,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import agent,model_client,model_settings
from agent import TOOLS

def cfg(provider):
    return {**model_settings.PRESETS[provider],"provider":provider,"enabled":True,"api_key":"test-placeholder","remember":False}

class ProviderAdapterTests(unittest.TestCase):
    def test_network_refusal_has_diagnostic_code_without_raw_reason(self):
        error=urllib.error.URLError(ConnectionRefusedError(10061,"test-placeholder-private-reason"))
        with patch.object(model_client,"open_model_request",side_effect=error):
            with self.assertRaises(model_client.ModelServiceError) as raised:
                model_client.send(cfg("deepseek"),[{"role":"user","content":"检查"}])
        self.assertEqual(raised.exception.code,"connection_refused")
        self.assertNotIn("test-placeholder",str(raised.exception))
    def test_openai_responses_roundtrip_preserves_tool_evidence(self):
        config=cfg("openai");requests=[]
        raw_output=[
            {"type":"reasoning","id":"opaque-reasoning","summary":[],"encrypted_content":"opaque-value"},
            {"type":"function_call","id":"fc1","call_id":"call1","name":"get_processing_rules","arguments":"{}"},
        ]
        def fake(req,timeout):
            payload=json.loads(req.data);requests.append(payload)
            self.assertTrue(req.full_url.endswith("/responses"))
            self.assertFalse(payload["store"])
            self.assertNotIn("max_tokens",payload)
            if len(requests)==1:
                self.assertEqual(payload["tool_choice"],{"type":"function","name":"get_processing_rules"})
                self.assertTrue(payload["tools"][0]["strict"])
                data={"status":"completed","output":raw_output}
            elif len(requests)==2:
                self.assertIn(raw_output[0],payload["input"])
                self.assertIn(raw_output[1],payload["input"])
                self.assertEqual(payload["input"][-1],{"type":"function_call_output","call_id":"call1","output":"连接测试工具已执行。本测试不包含实验数据。"})
                data={"status":"completed","output":[{"type":"message","role":"assistant","content":[{"type":"output_text","text":"工具往返成功"}]}]}
            else:
                self.assertEqual(payload["tool_choice"],{"type":"function","name":"route_question"})
                data={"status":"completed","output":[{"type":"function_call","call_id":"route-check","name":"route_question","arguments":'{"kind":"general"}'}]}
            return io.BytesIO(json.dumps(data).encode())
        with patch.object(agent,"effective",return_value=config),patch.object(model_client,"open_model_request",side_effect=fake):
            self.assertTrue(agent.test_connection()["ok"])
        self.assertEqual(len(requests),3)

    def test_mistral_forces_only_requested_tool(self):
        url,headers,payload,protocol=model_client.build_request(cfg("mistral"),[{"role":"user","content":"检查"}],TOOLS,{"type":"function","function":{"name":"get_processing_rules"}})
        self.assertEqual(payload["tool_choice"],"any")
        self.assertEqual([t["function"]["name"] for t in payload["tools"]],["get_processing_rules"])
        self.assertFalse(payload["parallel_tool_calls"])
        self.assertTrue(url.endswith("/chat/completions"))

    def test_gemini_carries_thought_signature_back(self):
        message={"role":"assistant","content":None,"extra_content":{"google":{"thought_signature":"opaque"}},"tool_calls":[{"id":"c1","type":"function","function":{"name":"get_processing_rules","arguments":"{}"},"extra_content":{"google":{"thought_signature":"nested"}}}]}
        history=model_client.assistant_history(message)
        _,_,payload,_=model_client.build_request(cfg("gemini"),[history,{"role":"tool","tool_call_id":"c1","content":"result"}],TOOLS)
        self.assertEqual(payload["messages"][0],message)
        self.assertNotIn("temperature",payload)

    def test_groq_and_openrouter_routing_options(self):
        _,_,g,_=model_client.build_request(cfg("groq"),[{"role":"user","content":"检查"}],TOOLS)
        self.assertEqual(g["reasoning_effort"],"low")
        _,_,o,_=model_client.build_request(cfg("openrouter"),[{"role":"user","content":"检查"}],TOOLS)
        self.assertTrue(o["provider"]["require_parameters"])

    def test_compatible_providers_complete_tool_roundtrip(self):
        for provider in ("deepseek","qwen","gemini","mistral","groq","openrouter"):
            with self.subTest(provider=provider):
                sent=[]
                def fake(req,timeout):
                    payload=json.loads(req.data);sent.append(payload)
                    if len(sent)==1:
                        message={"role":"assistant","content":None,"tool_calls":[{"id":"service-call","type":"function","function":{"name":"get_processing_rules","arguments":"{}"}}]}
                    elif len(sent)==2:
                        self.assertEqual(payload["messages"][-1]["tool_call_id"],"service-call")
                        message={"role":"assistant","content":"工具往返成功"}
                    else:
                        message={"role":"assistant","content":None,"tool_calls":[{"id":"route-check","type":"function","function":{"name":"route_question","arguments":'{"kind":"general"}'}}]}
                    return io.BytesIO(json.dumps({"choices":[{"message":message,"finish_reason":"stop"}]}).encode())
                with patch.object(agent,"effective",return_value=cfg(provider)),patch.object(model_client,"open_model_request",side_effect=fake):
                    self.assertTrue(agent.test_connection()["ok"])
                self.assertEqual(len(sent),3)

    def test_saved_key_is_not_reused_for_different_service_or_host(self):
        previous={**cfg("deepseek")}
        with patch.object(model_settings,"effective",return_value=previous):
            with self.assertRaises(ValueError):
                model_settings.save({"provider":"openai","enabled":True,"api_key":"","base_url":model_settings.PRESETS["openai"]["base_url"],"model":"gpt-4.1-mini"})
        with patch.object(model_settings,"effective",return_value={**cfg("custom"),"base_url":"http://127.0.0.1:9988"}):
            with self.assertRaises(ValueError):
                model_settings.save({"provider":"custom","enabled":True,"api_key":"","base_url":"http://127.0.0.1:9989","model":"local"})

    def test_presets_reject_unrelated_host_and_error_does_not_reveal_key(self):
        for p in ("openai","gemini","mistral","groq","openrouter"):
            with self.subTest(provider=p),self.assertRaises(ValueError):
                model_settings.validate({**cfg(p),"base_url":"https://example.com/v1"})
        error=urllib.error.HTTPError("https://example.com",401,"test-placeholder",{},io.BytesIO(b"test-placeholder"))
        with patch.object(model_client,"open_model_request",side_effect=error):
            with self.assertRaises(RuntimeError) as raised:
                model_client.send(cfg("openai"),[{"role":"user","content":"检查"}])
        self.assertNotIn("test-placeholder",str(raised.exception))

    def test_truncated_model_output_is_not_reported_as_success(self):
        with self.assertRaises(RuntimeError):
            model_client.normalize({"status":"incomplete","output":[]},"responses")
        with self.assertRaises(RuntimeError):
            model_client.normalize({"choices":[{"finish_reason":"length","message":{"content":"partial"}}]},"chat")

if __name__=="__main__":unittest.main()
