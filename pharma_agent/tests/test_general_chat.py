"""General questions answer normally without inheriting assay data or acquiring assay tools."""
import io,json,sys,unittest,threading,urllib.request
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import agent,model_settings,question_routing,server
from http.server import ThreadingHTTPServer

CFG={"enabled":True,"provider":"custom","base_url":"http://127.0.0.1:9988","model":"test-only","api_key":"dummy","remember":False}
class GeneralChatTests(unittest.TestCase):
    def test_general_wire_payload_excludes_tools_and_experiment_history(self):
        history=[{"role":"user","content":"Drug1 IC50 PRIVATE_RAW","intent":"analysis"},
            {"role":"assistant","content":"PRIVATE_FITTED_RESULT","intent":"analysis"},
            {"role":"assistant","content":"LEGACY_PRIVATE_RESULT"},
            {"role":"user","content":"介绍屠呦呦","intent":"general"},
            {"role":"assistant","content":"屠呦呦是科学家。","intent":"general"}]
        sent=[]
        def fake(request,timeout):
            payload=json.loads(request.data);sent.append(payload)
            names=[x['function']['name'] for x in payload.get('tools',[])]
            self.assertNotIn('get_analysis_results',names)
            self.assertIn('web_search',names)
            serialized=json.dumps(payload)
            for marker in ("PRIVATE_RAW","PRIVATE_FITTED_RESULT","LEGACY_PRIVATE_RESULT"):
                self.assertNotIn(marker,serialized)
            self.assertTrue(any(x.get("content")=="屠呦呦是科学家。" for x in payload["messages"]))
            return io.BytesIO(json.dumps({"choices":[{"message":{"role":"assistant","content":"她因青蒿素研究获奖。"},"finish_reason":"stop"}]}).encode())
        trace=[]
        with patch.object(agent,"effective",return_value=CFG),patch.object(__import__("model_client"),"open_model_request",side_effect=fake):
            answer=agent.general_answer("她为什么获奖？",trace,history)
        self.assertIn("青蒿素",answer)
        self.assertEqual(len(sent),1)
        self.assertEqual(trace[0]["step"],"通用回答")
    def test_general_failure_never_dumps_sample_results(self):
        with patch.object(agent,"config",return_value={"enabled":True}),patch.object(agent,"route_question",return_value="general"),patch.object(agent,"general_answer",side_effect=RuntimeError("模拟故障")),patch.object(agent,"local_answer") as local:
            answer,mode,error=agent.interpret([{"PRIVATE_DATA":"hidden"}],"讲一个笑话",[])
        local.assert_not_called()
        self.assertIn("通用回答未完成",answer)
        self.assertIn("失败",mode)
        self.assertEqual(error,"模拟故障")
    def test_disabled_general_model_is_explained_without_fake_answer(self):
        with patch.object(agent,"config",return_value={"enabled":False}),patch.object(agent,"general_answer") as model:
            answer,_,_=agent.interpret([],"介绍屠呦呦",[])
        self.assertIn("启用大模型",answer)
        self.assertNotIn("服务范围",answer)
        model.assert_not_called()
    def test_no_assay_data_does_not_prevent_general_or_method_question(self):
        with patch.object(agent,"config",return_value={"enabled":True}),patch.object(agent,"route_question",return_value="general"),patch.object(agent,"general_answer",return_value="可以直接回答人物介绍"):
            self.assertIn("人物",agent.interpret([],"介绍屠呦呦",[])[0])
        with patch.object(agent,"config",return_value={"enabled":False}):
            self.assertIn("四参数",agent.interpret([],"什么是4PL",[])[0])
            self.assertIn("先上传",agent.interpret([],"Drug4为什么没有IC50",[])[0])
    def test_general_followup_and_weather_knowledge_are_normal_questions(self):
        self.assertEqual(question_routing.local_route("她为什么获奖？",[{"role":"user","content":"介绍屠呦呦"}]),"general")
        self.assertEqual(question_routing.local_route("为什么下雨？"),"general")
        self.assertEqual(question_routing.local_route("南京今天会下雨吗？"),"realtime")
        self.assertEqual(question_routing.local_route("介绍一下光合作用"),"general")
    def test_generic_model_cannot_inject_experiment_tool_request(self):
        with patch.object(agent,"request_model",return_value={"content":"","tool_calls":[{"function":{"name":"get_analysis_results"}}]}):
            with self.assertRaisesRegex(ValueError,"无效"):
                agent.general_answer("介绍人物",[])

class GeneralChatAPITests(unittest.TestCase):
    def test_chat_before_upload_retains_general_context_and_response_mode(self):
        httpd=ThreadingHTTPServer(("127.0.0.1",0),server.Handler)
        thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
        def post(body):
            request=urllib.request.Request('http://127.0.0.1:'+str(httpd.server_port)+'/api/chat',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-AssayPilot-Token':__import__('local_access').ACCESS_TOKEN})
            with urllib.request.urlopen(request,timeout=3) as response:return json.load(response)
        def fake(results,question,trace,history):
            self.assertEqual(results,[])
            if question=="她呢？":
                self.assertEqual(history[0]["intent"],"general")
                self.assertEqual(history[1]["mode"],"通用问答")
            trace.append({"step":"范围判断","intent":"general"})
            return "一般知识回答","通用问答",None
        try:
            with patch.object(server,"CHAT_SESSIONS",{}),patch.object(server,"interpret",side_effect=fake):
                first=post({"question":"介绍屠呦呦"})
                second=post({"question":"她呢？","session":first["session"]})
                self.assertEqual(first["session"],second["session"])
                self.assertEqual(second["intent"],"general")
                self.assertEqual(len(server.CHAT_SESSIONS[first["session"]]["chat"]),4)
        finally:
            httpd.shutdown();httpd.server_close();thread.join()

if __name__=="__main__":unittest.main()
