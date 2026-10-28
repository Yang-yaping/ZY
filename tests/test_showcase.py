import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from coursework import load_questions
from showcase import ROOT, scene_configuration, render_showcase


class ShowcaseTests(unittest.TestCase):
    def test_four_original_assets_and_approved_titles(self):
        manifest=json.loads((ROOT/'static/scenes/manifest.json').read_text())
        config=scene_configuration()
        self.assertEqual([s['id'] for s in config['scenes']],['home','bank','nodes','coursework'])
        self.assertEqual(config['scenes'][0]['heading'],'课程作业')
        self.assertEqual(config['scenes'][0]['description'],'《密码货币与区块链技术》杨雅评课程作业')
        for scene in config['scenes']:
            data=(ROOT/'static/scenes'/scene['file']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),manifest[scene['id']]['sha256'])
        html=render_showcase(version='test')
        self.assertNotIn('__CONFIG__',html)
        self.assertIn('prefers-reduced-motion',html)
        self.assertNotIn('https://cdn',html)
        self.assertIn('transitionTo',html)

    def test_streamlit_visual_entrypoint_and_coursework_empty_state(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(len(app.get('bidi_component')),1)
        self.assertEqual(len(app.get('iframe')),0)
        app.switch_page('coursework_page.py').run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.session_state['_live_lab'].snapshot()['questions'],[])
        ui=(ROOT/'web/live/controller.js').read_text()
        self.assertNotIn("target = '_blank'",ui)
        self.assertIn("sender('action',request)",ui)

    def test_question_order_duplicate_validation_and_no_invented_questions(self):
        self.assertEqual(load_questions(),[])
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as folder:
            p=Path(folder)/'questions.json'
            p.write_text(json.dumps([{'id':3,'question':'三'},{'id':1,'question':'一','answer':'答'}]))
            self.assertEqual([q['id'] for q in load_questions(p)],[1,3])
            for bad in [[{'id':True,'question':'x'}],[{'id':1,'question':'x'},{'id':1,'question':'y'}],{}]:
                p.write_text(json.dumps(bad))
                with self.assertRaises(ValueError): load_questions(p)
