import sys, unittest, json, io
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import agent,model_settings
from analysis import analyze
ROOT=Path(__file__).resolve().parents[2]
DATA=next(p for p in ROOT.iterdir() if p.is_dir() and (p/"RAW DATA.csv").exists())
RAW=(DATA/"RAW DATA.csv").read_bytes()
REC=next(DATA.glob("*.xlsx")).read_bytes()
CFG={"enabled":True,"provider":"custom","base_url":"http://127.0.0.1:9988","model":"test-only","api_key":"dummy-test-key","remember":False}
class ModelTests(unittest.TestCase):
    def test_weather_question_is_explained_without_model_or_assay_payload(self):
        for question in ("今天天气怎么样？","南京明天会下雨吗？","What's the weather today?"):
            with self.subTest(question=question),patch.object(agent,"config",return_value={"enabled":False}),patch.object(agent,"model_answer") as model,patch.object(agent,"realtime_answer",return_value=("查询结果","联网查询",None)) as query:
                trace=[]
                answer,mode,error=agent.interpret([],question,trace)
                model.assert_not_called()
                self.assertIn("查询结果",answer)
                self.assertNotIn("Z′=",answer)
                self.assertIn("联网查询",mode)
                query.assert_called_once()
                self.assertIsNone(error)
                self.assertEqual(trace[0]["step"],"范围判断")
    def test_weather_in_assay_question_keeps_evidence_path(self):
        self.assertIsNone(agent.scope_reply("天气温度变化会影响这个细胞实验吗？"))
        self.assertIsNone(agent.scope_reply("Weather and temperature effects on the assay?"))
        self.assertIsNone(agent.scope_reply("为什么Drug4没有IC50？"))
    def test_all_official_presets_offer_choices_and_keep_default(self):
        for provider,preset in model_settings.PRESETS.items():
            if provider=="custom":continue
            with self.subTest(provider=provider):
                self.assertGreaterEqual(len(set(preset["models"])),2)
                self.assertIn(preset["model"],preset["models"])
    def test_greeting_and_obvious_outside_question_have_scope_reply(self):
        self.assertIn("你好",agent.scope_reply("你好！"))
        self.assertIsNone(agent.scope_reply("推荐电影"))
        self.assertIsNone(agent.scope_reply("帮我比较样品"))
    def test_model_calls_tool_then_answers(self):
        result=analyze(RAW,REC);trace=[];calls=[]
        def fake(req,timeout):
            payload=json.loads(req.data);calls.append(payload)
            if len(calls)==1:
                self.assertFalse(any(m["role"]=="tool" for m in payload["messages"]))
                self.assertEqual(payload["tool_choice"]["function"]["name"],"get_analysis_results")
                message={"role":"assistant","content":None,"tool_calls":[{"id":"real-id-1","type":"function","function":{"name":"get_analysis_results","arguments":"{}"}}]}
            else:
                self.assertEqual(payload["messages"][-1]["tool_call_id"],"real-id-1")
                evidence=json.loads(payload["messages"][-1]["content"])
                self.assertAlmostEqual(evidence[0]["samples"][0]["ic50_nm"],3.2,delta=.03)
                message={"role":"assistant","content":"依据工具，Drug4不可可靠估计。"}
            return io.BytesIO(json.dumps({"choices":[{"message":message}]}).encode())
        with patch.object(agent,"effective",return_value=CFG),patch.object(__import__("model_client"),"open_model_request",side_effect=fake):
            text=agent.model_answer([result],"解释Drug4",trace)
        self.assertIn("Drug4",text);self.assertEqual(len(calls),2);self.assertEqual(trace[0]["tool"],"get_analysis_results")
    def test_model_without_tool_is_not_reported_as_success(self):
        with patch.object(agent,"effective",return_value=CFG),patch.object(agent,"request_model",return_value={"role":"assistant","content":"无依据回答"}):
            with self.assertRaisesRegex(RuntimeError,"工具调用"):agent.model_answer([analyze(RAW,REC)],"问题",[])
    def test_model_failure_retains_real_results(self):
        with patch.object(agent,"config",return_value={"enabled":True}),patch.object(agent,"route_question",return_value="analysis"),patch.object(agent,"model_answer",side_effect=RuntimeError("模拟服务故障")):
            text,mode,error=agent.interpret([analyze(RAW,REC)],"Drug4",[])
        self.assertIn("降级",mode);self.assertIn("Drug4",text);self.assertIsNotNone(error)
    def test_connection_checks_tool_roundtrip(self):
        first={"role":"assistant","content":None,"tool_calls":[{"id":"check","type":"function","function":{"name":"get_processing_rules","arguments":"{}"}}]}
        routed={"role":"assistant","content":None,"tool_calls":[{"id":"route","type":"function","function":{"name":"route_question","arguments":'{"kind":"general"}'}}]}
        with patch.object(agent,"effective",return_value=CFG),patch.object(agent,"request_model",side_effect=[first,{"role":"assistant","content":"确认成功"},routed]) as mock:
            self.assertTrue(agent.test_connection()["ok"])
            self.assertEqual(mock.call_count,3)
    def test_public_config_does_not_expose_key(self):
        with patch.object(model_settings,"effective",return_value=CFG):
            c=model_settings.public()
        self.assertTrue(c["has_key"]);self.assertNotIn("api_key",c)
        self.assertNotIn("dummy-test-key",json.dumps(c))
    def test_non_https_external_service_is_rejected(self):
        with self.assertRaises(ValueError):model_settings.validate({**CFG,"base_url":"http://example.com"})
    def test_preset_blocks_wrong_host(self):
        with self.assertRaises(ValueError):model_settings.validate({**CFG,"provider":"deepseek","base_url":"https://example.com"})
    def test_foreign_presets_use_official_hosts(self):
        for name,host in [("openai","api.openai.com"),("gemini","generativelanguage.googleapis.com"),("mistral","api.mistral.ai"),("groq","api.groq.com"),("openrouter","openrouter.ai")]:
            cfg=dict(model_settings.PRESETS[name],provider=name,enabled=True,api_key="test",remember=False)
            self.assertEqual(model_settings.validate(cfg)["base_url"],model_settings.PRESETS[name]["base_url"])
            self.assertIn(host,cfg["base_url"])
    def test_windows_key_encryption_roundtrip(self):
        import os
        if os.name!="nt":self.skipTest("Windows only")
        text=b"test-only-not-real-key"
        encrypted=model_settings.protect(text)
        self.assertNotEqual(encrypted,text)
        self.assertEqual(model_settings.protect(encrypted,True),text)
if __name__=="__main__":unittest.main()
