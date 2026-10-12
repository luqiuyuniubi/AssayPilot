"""Intent policy, context, strict routing and provider contracts without paid API calls."""
import sys,json,io,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import agent,model_client,model_settings,question_routing as routing

CFG={"enabled":True,"provider":"custom","base_url":"http://127.0.0.1:9988","model":"test-only","api_key":"dummy-test-key","remember":False}
def selected(kind):
    return {"role":"assistant","content":None,"tool_calls":[{"id":"route-1","type":"function","function":{"name":"route_question","arguments":json.dumps({"kind":kind})}}]}

class RoutingTests(unittest.TestCase):
    def test_explicit_topics_are_not_mislabelled_as_missing_sample(self):
        for question in ("请介绍一下屠呦呦","能不能讲讲爱因斯坦","请解释一下黑洞","帮我写一个购物清单","屠呦呦是谁？"):
            with self.subTest(question=question):
                self.assertEqual(routing.local_route(question),"general")
                self.assertIsNone(routing.routing_reply("general",question))
        self.assertEqual(routing.explicit_subject("请介绍一下屠呦呦"),"屠呦呦")
        self.assertEqual(routing.local_route("请介绍一下IC50"),"method")
        self.assertEqual(routing.local_route("请介绍一下Drug4"),"analysis")
    def test_vague_pronouns_and_unrecognised_text_have_different_fallbacks(self):
        for question in ("它怎么了？","那个怎么弄？","请介绍一下那个"):
            self.assertEqual(routing.local_route(question),"clarify")
        kind=routing.local_route("量子涨落与文明的边界")
        self.assertEqual(kind,"general")
        self.assertIsNone(routing.routing_reply(kind,"量子涨落与文明的边界"))
    def test_routing_failure_retains_safe_diagnostic_and_explicit_topic(self):
        error=model_client.ModelServiceError("模型连接被拒绝","connection_refused")
        with patch.object(agent,"config",return_value={"enabled":True}),patch.object(agent,"route_question",side_effect=error):
            trace=[];text,_,failure=agent.interpret([],"请介绍一下屠呦呦",trace)
        self.assertIn("模型连接",text)
        self.assertNotIn("具体样品",text)
        self.assertEqual(trace[0]["intent"],"general")
        self.assertEqual(trace[0]["error"]["code"],"connection_refused")
        self.assertIn("连接被拒绝",failure)
    def test_none_tool_calls_is_a_clear_routing_error(self):
        with self.assertRaisesRegex(ValueError,"路由工具"):
            routing.parse_route({"tool_calls":None,"content":"plain text"})
    def test_semantic_outside_question_does_not_read_experiment_results(self):
        # No old weather/movie keywords: prove the semantic router can handle an unseen domain.
        with patch.object(agent,"config",return_value={"enabled":True}),patch.object(agent,"request_model",side_effect=[selected("general"),{"role":"assistant","content":"修剪盆栽前先确认植物品种，去掉枯枝。"}]) as request,patch.object(agent,"model_answer") as analysis:
            trace=[];text,mode,error=agent.interpret([{"SECRET_ASSAY_PAYLOAD":"private"}],"如何修剪阳台上的盆栽？",trace)
        analysis.assert_not_called()
        self.assertIn("枯枝",text)
        self.assertNotIn("private",json.dumps(request.call_args.args))
        self.assertEqual(trace[0]["intent"],"general")
        self.assertIn("通用问答",mode)
        self.assertIsNone(error)
    def test_each_scoped_route_responds_without_analysis_tool(self):
        for kind,question in [("smalltalk","你今天精神怎么样？"),("clarify","它怎么了？"),("realtime","南京今天气温多少？")]:
            with self.subTest(kind=kind),patch.object(agent,"config",return_value={"enabled":True}),patch.object(agent,"request_model",return_value=selected(kind)),patch.object(agent,"model_answer") as analysis,patch.object(agent,"realtime_answer",return_value=("联网结果","联网查询",None)):
                text,_,_=agent.interpret([],question,[])
                self.assertTrue(text)
                analysis.assert_not_called()
    def test_analysis_and_method_routes_keep_evidence_calls(self):
        for kind in ("analysis","method"):
            with self.subTest(kind=kind),patch.object(agent,"config",return_value={"enabled":True}),patch.object(agent,"request_model",return_value=selected(kind)),patch.object(agent,"model_answer",return_value="工具解读") as analysis:
                text,_,_=agent.interpret([{"results":"sentinel"}],"请解释这个问题",[])
                self.assertEqual(text,"工具解读")
                self.assertEqual(analysis.call_args.kwargs["method"],kind=="method")
    def test_router_failure_clarifies_instead_of_dumping_assay(self):
        with patch.object(agent,"config",return_value={"enabled":True}),patch.object(agent,"route_question",side_effect=RuntimeError("路由连接失败")),patch.object(agent,"model_answer") as analysis:
            trace=[];text,mode,error=agent.interpret([],"那个怎么弄？",trace)
        self.assertIn("具体样品",text)
        self.assertIn("降级",mode)
        self.assertEqual(trace[0]["status"],"降级")
        self.assertEqual(error,"路由连接失败")
        analysis.assert_not_called()
    def test_ambiguous_followup_uses_latest_user_topic(self):
        self.assertEqual(routing.local_route("为什么呢？"),"clarify")
        self.assertEqual(routing.local_route("为什么呢？",[{"role":"user","content":"Drug4为什么没有IC50？"}]),"analysis")
        self.assertEqual(routing.local_route("为什么呢？",[{"role":"user","content":"Drug4是什么"},{"role":"user","content":"今天天气怎么样"}]),"clarify")
    def test_local_glossary_answers_method_without_sample_dump(self):
        with patch.object(agent,"config",return_value={"enabled":False}):
            text,mode,_=agent.interpret([],"什么是4PL和IC50？",[])
        self.assertIn("四参数",text)
        self.assertIn("一般方法说明",text)
        self.assertNotIn("Drug1：",text)
        self.assertIn("本地方法",mode)
    def test_social_thanks_and_goodbye_are_distinct(self):
        with patch.object(agent,"config",return_value={"enabled":True}),patch.object(agent,"request_model") as model:
            self.assertIn("不客气",agent.interpret([],"谢谢你！",[])[0])
            self.assertIn("再见",agent.interpret([],"再见！",[])[0])
            self.assertIn("AssayPilot",agent.interpret([],"你是谁？",[])[0])
        model.assert_not_called()
    def test_routing_context_excludes_assistant_experimental_summary(self):
        messages=routing.routing_messages("那它呢？",[{"role":"user","content":"Drug4情况"},{"role":"assistant","content":"SECRET_RESULT_VALUE"}])
        text=json.dumps(messages)
        self.assertIn("Drug4",text)
        self.assertNotIn("SECRET_RESULT_VALUE",text)
    def test_invalid_or_injected_route_is_rejected(self):
        for args in ({"kind":"run_shell"},{"kind":"analysis","extra":"secret"},[],{"kind":["analysis"]}):
            with self.subTest(args=args):
                message=selected("analysis");message["tool_calls"][0]["function"]["arguments"]=json.dumps(args)
                with self.assertRaises(ValueError):routing.parse_route(message)
        with self.assertRaises(ValueError):routing.parse_route({"content":"analysis"})
    def test_all_provider_routing_tools_use_valid_schema_and_parse(self):
        for provider in ("openai","deepseek","qwen","gemini","mistral","groq","openrouter"):
            config={**model_settings.PRESETS[provider],"provider":provider,"enabled":True,"api_key":"test-placeholder","remember":False}
            def fake(req,timeout):
                payload=json.loads(req.data)
                tool=payload["tools"][0]
                schema=tool["parameters"] if provider=="openai" else tool["function"]["parameters"]
                self.assertEqual(schema["required"],["kind"])
                if provider=="openai":
                    response={"status":"completed","output":[{"type":"function_call","call_id":"r1","name":"route_question","arguments":'{"kind":"general"}'}]}
                else:response={"choices":[{"message":selected("general"),"finish_reason":"stop"}]}
                return io.BytesIO(json.dumps(response).encode())
            with self.subTest(provider=provider),patch.object(agent,"effective",return_value=config),patch.object(model_client,"open_model_request",side_effect=fake):
                self.assertEqual(agent.route_question("如何照顾盆栽"),"general")
    def test_method_reads_rules_before_answering(self):
        responses=[{"role":"assistant","content":None,"tool_calls":[{"id":"rules-1","type":"function","function":{"name":"get_processing_rules","arguments":"{}"}}]},{"role":"assistant","content":"一般方法：4PL是四参数模型。"}]
        with patch.object(agent,"effective",return_value=CFG),patch.object(agent,"request_model",side_effect=responses) as model:
            text=agent.model_answer([{"rules":{"fit":"4PL"}}],"什么是4PL？",[],method=True)
        self.assertEqual(model.call_args_list[0].args[2]["function"]["name"],"get_processing_rules")
        self.assertIn("一般方法",text)

if __name__=="__main__":unittest.main()
