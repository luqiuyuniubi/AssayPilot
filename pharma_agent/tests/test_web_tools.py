import io,json,socket,sys,unittest
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import agent,public_web,web_tools,web_settings

class WebToolsTests(unittest.TestCase):
    def test_private_url_and_dns_are_blocked_before_connect(self):
        for url in ('http://localhost','http://127.0.0.1','http://169.254.169.254','http://[::1]','http://224.0.0.1','https://example.com:8765','file:///C:/secret','https://user:pass@example.com'):
            with self.subTest(url=url),self.assertRaises(public_web.PublicWebError):public_web.validate_public_url(url)
        with patch.object(socket,'getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.0.0.1',443))]):
            with self.assertRaises(public_web.PublicWebError):public_web.validate_public_url('https://example.com')
    def test_connection_uses_validated_address_not_second_dns_lookup(self):
        response=Mock(status=200);response.read.return_value=b'hello';response.getheaders.return_value=[('Content-Type','text/plain')]
        conn=Mock();conn.getresponse.return_value=response
        parsed=__import__('urllib.parse',fromlist=['urlparse']).urlparse('https://example.com/page')
        with patch.object(public_web,'validate_public_url',return_value=(parsed,['93.184.216.34'])),patch.object(public_web.http.client,'HTTPSConnection',return_value=conn),patch.object(public_web.socket,'create_connection') as connect:
            public_web.request_public('https://example.com/page')
            conn._create_connection(('example.com',443),15)
        self.assertEqual(connect.call_args.args[0],('93.184.216.34',443))
    def test_redirect_revalidates_and_never_forwards_credentials(self):
        response=Mock(status=302);response.getheader.return_value='http://127.0.0.1/secret'
        conn=Mock();conn.getresponse.return_value=response
        parsed=__import__('urllib.parse',fromlist=['urlparse']).urlparse('https://example.com')
        with patch.object(public_web,'validate_public_url',side_effect=[(parsed,['93.184.216.34']),public_web.PublicWebError('private')]),patch.object(public_web.http.client,'HTTPSConnection',return_value=conn):
            with self.assertRaises(public_web.PublicWebError):public_web.request_public('https://example.com')
        with patch.object(public_web,'validate_public_url',return_value=(parsed,['93.184.216.34'])),patch.object(public_web.http.client,'HTTPSConnection',return_value=conn):
            with self.assertRaisesRegex(public_web.PublicWebError,'密钥'):public_web.request_public('https://example.com',{'Authorization':'Bearer private'})
    def test_page_reader_extracts_visible_text_and_not_scripts(self):
        raw=('<html><title>Example</title><script>PRIVATE_SCRIPT</script><style>PRIVATE_STYLE</style><article>'+'Readable page content. '*20+'</article></html>').encode()
        with patch.object(web_tools,'validate_public_url'),patch.object(web_tools,'request_public',return_value=(raw,{'Content-Type':'text/html; charset=utf-8'},'https://example.com')):
            data=web_tools.read_webpage('https://example.com')
        self.assertEqual(data['title'],'Example');self.assertNotIn('PRIVATE_SCRIPT',data['text']);self.assertNotIn('PRIVATE_STYLE',data['text'])
    def test_search_public_is_explicit_about_unreliable_freshness(self):
        raw=b'<rss><channel><item><title>Title</title><link>https://example.com</link><description>Snippet</description></item></channel></rss>'
        with patch.object(web_tools,'search_config',return_value={'provider':'public','api_key':''}),patch.object(web_tools,'request_public',return_value=(raw,{},'https://www.bing.com')):
            data=web_tools.web_search('query',2,'day')
        self.assertFalse(data['freshness_applied']);self.assertEqual(data['results'][0]['url'],'https://example.com')
    def test_tavily_and_brave_use_separate_service_key_and_normalise(self):
        for provider in ('tavily','brave'):
            out={'results':[{'title':'A','url':'https://example.com','content':'snippet'}]} if provider=='tavily' else {'web':{'results':[{'title':'A','url':'https://example.com','description':'snippet'}]}}
            with self.subTest(provider=provider),patch.object(web_tools,'search_config',return_value={'provider':provider,'api_key':'search-private'}),patch.object(web_tools,'json_request',return_value=out) as request:
                data=web_tools.web_search('public query',2,'week')
                self.assertEqual(data['results'][0]['snippet'],'snippet')
                self.assertNotIn('search-private',json.dumps(data))
                self.assertIn('search-private',str(request.call_args.args[1]))
    def test_public_config_and_service_switch_do_not_expose_or_reuse_key(self):
        old={'provider':'tavily','api_key':'private-key','remember':False}
        with patch.object(web_settings,'effective',return_value=old):
            self.assertNotIn('private-key',json.dumps(web_settings.public()))
            with self.assertRaises(ValueError):web_settings.save({'provider':'brave','api_key':''})
    def test_currency_reports_date_and_not_realtime_quote(self):
        with patch.object(web_tools,'json_request',return_value={'date':'2026-10-09','rates':{'CNY':7}}):
            data=web_tools.exchange_rate('USD','CNY',10)
        self.assertEqual(data['converted'],70);self.assertIn('2026-10-09',web_tools.render_web('exchange_rate',data));self.assertIn('不是交易',data['note'])
        with self.assertRaises(ValueError):web_tools.exchange_rate('USD','CNY',float('nan'))
    def test_paper_metadata_has_title_and_doi(self):
        out={'message':{'items':[{'type':'component','title':['Supporting data'],'DOI':'10.1000/data','URL':'https://doi.org/10.1000/data'},{'title':['Example paper'],'DOI':'10.1000/example','URL':'https://doi.org/10.1000/example','issued':{'date-parts':[[2025]]}}]}}
        with patch.object(web_tools,'json_request',return_value=out):data=web_tools.search_papers('test')
        self.assertEqual(data['papers'][0]['year'],2025);self.assertIn('元数据',data['note'])
    def test_general_tool_roundtrip_keeps_source_and_excludes_assay(self):
        call={'role':'assistant','content':None,'tool_calls':[{'id':'web1','function':{'name':'web_search','arguments':'{"query":"test","limit":2,"freshness":"any"}'}}]}
        out={'results':[{'url':'https://example.com','title':'test','snippet':'text'}],'queried_at':'time'}
        with patch.object(agent,'request_model',side_effect=[call,{'role':'assistant','content':'Based on the search.'}]) as model,patch.object(agent,'execute_web',return_value=out):
            trace=[];answer=agent.general_answer('search',trace,[{'role':'assistant','intent':'analysis','content':'PRIVATE_RESULTS'}])
        self.assertIn('https://example.com',answer);self.assertNotIn('PRIVATE_RESULTS',json.dumps(model.call_args_list[0].args))
        self.assertEqual(model.call_args_list[1].args[0][-1]['tool_call_id'],'web1');self.assertEqual(trace[0]['tool'],'web_search')

if __name__=='__main__':unittest.main()
