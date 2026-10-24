"""ROS-free boundary tests for process replay and local read-only HTTP."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest


class ViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import view_process
        except ImportError:
            view_process = None
        cls.viewer = view_process

    def setUp(self):
        self.assertIsNotNone(self.viewer, 'view_process must provide offline export and a fixed-route read-only server')
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.run = Path(self.folder.name)
        self.document = {'version':1,'coordinate_frame':'map','scenario':{'name':'</script><img src=x onerror=alert(1)>'},
                         'frames':[{'t':1,'wall_t':2,'pose':[0,0,0],'map':None,'status':{}}],
                         'maps':[],'path':[[999,999]],'statuses':[],'terminal':None}
        (self.run/'process.json').write_text(json.dumps(self.document))

    def test_export_embeds_data_and_optional_final_assessment_without_script_injection(self):
        (self.run/'result.json').write_text(json.dumps({'success':False,'saved_map_metrics':{'reachable_coverage':.7}}))
        output = self.viewer.export_replay(self.run/'process.json')
        text = output.read_text()
        self.assertIn('\\u003c/script>', text)
        self.assertNotIn('</script><img', text)
        self.assertIn('"reachable_coverage":0.7', text)
        self.assertIn('process-data', text)
        self.assertNotIn('src="http', text)

    def test_export_supports_missing_result_and_no_frames(self):
        self.document['frames']=[]
        (self.run/'process.json').write_text(json.dumps(self.document))
        output=self.viewer.export_replay(self.run/'process.json')
        self.assertIn('等待第一帧',output.read_text())
        self.assertIn('本次最终评分',output.read_text())

    def test_fixed_routes_refuse_traversal_post_symlink_and_arbitrary_files(self):
        (self.run/'secret.txt').write_text('secret')
        server=self.viewer.make_server(self.run,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def request(method,path,headers=None):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
            connection.request(method,path,headers=headers or {})
            response=connection.getresponse()
            payload=response.read()
            connection.close()
            return response.status,payload
        self.assertEqual(server.server_address[0],'127.0.0.1')
        self.assertEqual(request('GET','/')[0],200)
        self.assertEqual(json.loads(request('GET','/process.json')[1]),self.document)
        for path in ('/secret.txt','/../secret.txt','/%2e%2e/secret.txt','/process.json/../secret.txt','/truth.json'):
            self.assertEqual(request('GET',path)[0],404,path)
        self.assertEqual(request('POST','/process.json')[0],405)
        self.assertEqual(request('GET','/',{'Host':'evil.example'})[0],403)
        outside=self.run.parent/('outside-'+self.run.name+'.json')
        outside.write_text('{"secret":true}')
        self.addCleanup(outside.unlink)
        (self.run/'result.json').symlink_to(outside)
        self.assertEqual(request('GET','/result.json')[0],404)

    def test_export_preserves_marker_like_text_inside_recorded_metadata(self):
        import re
        self.document['scenario']['name']='__RESULT_DATA__ __LIVE_DATA__'
        (self.run/'process.json').write_text(json.dumps(self.document))
        output=self.viewer.export_replay(self.run/'process.json')
        payload=re.search(r'<script id="process-data" type="application/json">(.*?)</script>',output.read_text(),re.S)[1]
        self.assertEqual(json.loads(payload),self.document)
    def test_invalid_version_does_not_generate_misleading_replay(self):
        self.document['version']=99
        (self.run/'process.json').write_text(json.dumps(self.document))
        with self.assertRaisesRegex(ValueError,'version'):
            self.viewer.export_replay(self.run/'process.json')


if __name__=='__main__':
    unittest.main()
