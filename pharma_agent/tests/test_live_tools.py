import io,json,sys,unittest,urllib.error
from datetime import timedelta
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import live_tools as live,agent

def feed(title='今日科技进展',when=None,link='https://www.chinanews.com.cn/test/1.shtml'):
    when=when or live.now()
    return ('<rss><channel><item><title>'+title+'</title><link>'+link+'</link><pubDate>'+format_datetime(when)+'</pubDate></item></channel></rss>').encode()

class LiveToolsTests(unittest.TestCase):
    def test_local_realtime_route_keeps_news_topic_and_weather_followup(self):
        from question_routing import local_route
        self.assertEqual(local_route('最近医药新闻有哪些？'),'realtime')
        self.assertEqual(local_route('那明天呢？',[{'role':'user','content':'南京今天天气'}]),'realtime')
    def test_weather_values_dates_and_sources_are_preserved(self):
        geo={'results':[{'name':'南京','admin1':'江苏','country':'中国','latitude':32,'longitude':118,'population':10000}]}
        forecast={'timezone':'Asia/Shanghai','current':{'time':'2026-10-10T12:00','temperature_2m':24.5,'weather_code':0},
          'daily':{'time':['2026-10-10','2026-10-11'],'weather_code':[0,61],'temperature_2m_max':[25,23],'temperature_2m_min':[16,15],'precipitation_probability_max':[0,80]}}
        with patch.object(live,'get_json',side_effect=[(geo,'geo-time'),(forecast,'query-time')]) as query:
            result=live.get_weather('南京',days=1,day_offset=1)
        self.assertEqual(result['forecast'][0]['date'],'2026-10-11')
        self.assertEqual(result['current']['temperature_c'],24.5)
        self.assertIn('Open-Meteo',live.render_live('get_weather',result))
        self.assertIn('query-time',live.render_live('get_weather',result))
        self.assertIn('forecast_days=2',query.call_args.args[0])
    def test_bad_weather_location_and_tool_parameters_are_rejected(self):
        for city,days,offset in [('',1,0),('南京',0,0),('南京',1,-1),('南京',True,0)]:
            with self.assertRaises(ValueError):live.get_weather(city,days,offset)
        with self.assertRaises(ValueError):live.execute('run_shell',{})
        with self.assertRaises(ValueError):live.execute('get_weather',{'location':'南京','days':1,'day_offset':0,'url':'http://127.0.0.1'})
    def test_missing_or_ambiguous_city_requests_clarification(self):
        plan,text=live.fallback_plan('今天天气怎么样？')
        self.assertIsNone(plan);self.assertIn('哪个城市',text)
        with patch.object(live,'get_json',return_value=({'results':[]},'time')):
            self.assertTrue(live.get_weather('unknown')['needs_location'])
    def test_relative_weather_followup_uses_requested_city(self):
        history=[{'role':'user','content':'南京今天天气','intent':'realtime'}]
        plan,_=live.fallback_plan('那明天呢？',history)
        self.assertEqual(plan[1],{'location':'南京','days':1,'day_offset':1})
    def test_news_filters_stale_and_unmatched_items(self):
        raw=feed('人工智能发展')
        with patch.object(live,'fetch',return_value=(raw,'queried')):
            result=live.search_news(topic='人工智能')
        self.assertEqual(len(result['articles']),1)
        self.assertIn('发布时间',live.render_live('search_news',result))
        with patch.object(live,'fetch',return_value=(feed(when=live.now()-timedelta(days=8)),'queried')):
            self.assertFalse(live.search_news()['articles'])
        with patch.object(live,'fetch',return_value=(raw,'queried')):
            text=live.render_live('search_news',live.search_news(topic='不存在的主题'))
        self.assertIn('不代表全网没有',text)
    def test_xml_entities_and_non_web_links_are_rejected(self):
        with self.assertRaises(live.LiveToolError):live.parse_news(b'<!DOCTYPE a><rss/>','source','time')
        self.assertEqual(live.parse_news(feed(link='javascript:alert(1)'),'source','time'),[])
        self.assertFalse(live.safe_link('https://user:secret@example.com'))
    def test_fixed_endpoints_prevent_arbitrary_fetch_and_redirect(self):
        for url in ('http://127.0.0.1','https://example.com','file:///C:/secret'):
            with self.assertRaises(live.LiveToolError):live.fetch(url)
        with self.assertRaises(live.LiveToolError):live.SafeRedirect().redirect_request(None,None,302,'',{},'http://127.0.0.1')
    def test_successful_public_fetch_is_cached_with_original_query_time(self):
        url='https://api.open-meteo.com/test-only'
        opener=unittest.mock.Mock();opener.open.return_value=io.BytesIO(b'{}')
        with patch.object(live,'CACHE',{}),patch.object(live.urllib.request,'build_opener',return_value=opener):
            first=live.fetch(url);second=live.fetch(url)
        self.assertEqual(first,second);opener.open.assert_called_once()
    def test_failed_live_query_never_uses_general_model_memory(self):
        with patch.object(agent,'execute_live',side_effect=live.LiveToolError('测试失败')),patch.object(agent,'general_answer') as general:
            trace=[];text,mode,error=agent.realtime_answer('南京天气',trace,enabled=False)
        self.assertIn('不会用模型记忆',text);self.assertIn('失败',mode);self.assertTrue(error)
        general.assert_not_called();self.assertEqual(trace[-1]['status'],'失败')
    def test_weather_request_uses_live_tool_not_experiment_context(self):
        request={'role':'assistant','content':None,'tool_calls':[{'function':{'name':'get_weather','arguments':json.dumps({'location':'南京','days':1,'day_offset':0})}}]}
        with patch.object(agent,'request_model',return_value=request) as model,patch.object(agent,'execute_live',return_value={'queried_at':'time','source_url':'https://api.open-meteo.com/','forecast':[{}]}),patch.object(agent,'render_live',return_value='天气数据'):
            trace=[];text,_,_=agent.realtime_answer('南京天气',trace,[{'role':'assistant','intent':'analysis','content':'PRIVATE_EXPERIMENT'}],True)
        self.assertNotIn('PRIVATE_EXPERIMENT',json.dumps(model.call_args.args))
        self.assertEqual(text,'天气数据');self.assertEqual(trace[-1]['tool'],'get_weather')

if __name__=='__main__':unittest.main()
