import json
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from live_lab import LiveLab
from ecash.runtime import DEMO_PASSWORD


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.lab=LiveLab(Path(self.tmp.name))
    def tearDown(self): self.tmp.cleanup()
    def command(self,action,**payload):
        result=self.lab.handle({'id':secrets.token_hex(12),'action':action,'payload':payload})
        self.assertTrue(result['ok'],result)
        return result
    def payer(self,action,**kw):return self.command(action,name='alice',password=DEMO_PASSWORD,**kw)
    def merchant(self,action,name='shop_a',**kw):return self.command(action,name=name,password=DEMO_PASSWORD,**kw)
    def withdraw(self):
        wid=self.payer('prepare',n=4,t=8)['wallet_id']
        self.payer('submit',wid=wid);self.payer('issue',wid=wid)
        return wid
    def pay(self,wid,name,bit,double=False):
        with patch('ecash.actors.secrets.randbits',return_value=bit):
            pid=self.merchant('offer',name,owner='alice',wid=wid)['payment_id']
        self.payer('respond',wid=wid,pid=pid,merchant=name,double=double)
        self.merchant('accept',name,pid=pid)
        return self.merchant('deposit',name,pid=pid)['deposit']

    def test_live_legal_payment_and_double_spend_recovery(self):
        wid=self.withdraw()
        self.assertEqual(self.pay(wid,'shop_a',0)['status'],'CREDITED')
        self.assertEqual(self.pay(wid,'shop_b',1,True)['status'],'DOUBLE_SPEND_IDENTIFIED')
        snapshot=self.lab.snapshot()
        self.assertEqual(snapshot['bank']['evidence'][0]['names'],['alice'])
        self.assertEqual({a['name']:a['balance'] for a in snapshot['bank']['accounts']},{'alice':90,'shop_a':10,'shop_b':0})
        self.assertEqual(snapshot['wallets']['alice'][0]['state'],'SPENT')
        serial=snapshot['wallets']['alice'][0]['cash']['coin']['serial']
        self.assertNotIn(serial,json.dumps(snapshot['bank']['issuance']))

    def test_identical_challenge_boundary_and_wallet_guard(self):
        wid=self.withdraw();self.pay(wid,'shop_a',0)
        with patch('ecash.actors.secrets.randbits',return_value=0):pid=self.merchant('offer','shop_b',owner='alice',wid=wid)['payment_id']
        denied=self.lab.handle({'id':secrets.token_hex(12),'action':'respond','payload':dict(name='alice',password=DEMO_PASSWORD,wid=wid,pid=pid,merchant='shop_b',double=False)})
        self.assertFalse(denied['ok'])
        self.payer('respond',wid=wid,pid=pid,merchant='shop_b',double=True)
        self.merchant('accept','shop_b',pid=pid)
        result=self.merchant('deposit','shop_b',pid=pid)['deposit']
        self.assertEqual(result['status'],'DUPLICATE_SAME_CHALLENGE');self.assertIsNone(result['identity'])

    def test_event_replay_and_invalid_input(self):
        event={'id':'fresh-command-id','action':'prepare','payload':dict(name='alice',password=DEMO_PASSWORD,n=4,t=8)}
        first=self.lab.handle(event);self.assertTrue(first['ok']);self.assertEqual(self.lab.handle(event),first)
        self.assertEqual(len(self.lab.snapshot()['wallets']['alice']),1)
        for action,payload in [('prepare',dict(name='alice',password=DEMO_PASSWORD,n=True,t=8)),('account_active',dict(name='alice',active='false')),('p2p_run',dict(size=1,count=3,profile='normal',optimized=True,workers=4)),('answer_save',dict(qid=1,answer='fake'))]:
            result=self.lab.handle({'id':secrets.token_hex(12),'action':action,'payload':payload})
            self.assertFalse(result['ok'],result)

    def test_forgery_and_no_private_material_in_snapshot(self):
        wid=self.withdraw()
        self.assertEqual(self.merchant('verify_forgery',owner='alice',wid=wid)['verification'],'REJECTED')
        snapshot=self.lab.snapshot();self.assertEqual(snapshot['payments']['shop_a'],[])
        encoded=json.dumps(snapshot)
        for secret in ['"opening"','"candidates"','"password"','"salt"','"d"']:self.assertNotIn(secret,encoded)
        self.assertNotIn(self.lab.bank.key()['d'],encoded)

    def test_account_controls_and_cancellation(self):
        self.command('account_create',name='student',password='student-password',kind='payer')
        self.command('account_active',name='student',active=False)
        bad=self.lab.handle({'id':secrets.token_hex(12),'action':'prepare','payload':dict(name='student',password='student-password',n=4,t=8)})
        self.assertFalse(bad['ok'])
        wid=self.payer('prepare',n=4,t=8)['wallet_id'];self.payer('submit',wid=wid);self.payer('cancel',wid=wid)
        self.assertEqual(self.lab.bank.account('alice',DEMO_PASSWORD)['balance'],100)

    def test_actual_p2p_counts_and_saved_answer(self):
        for count in (1,2,3,10):
            self.command('p2p_run',size=65536,count=count,profile='normal',optimized=True,workers=4)
            self.assertEqual(self.lab.result['sync']['height'],count)
            self.assertTrue(self.lab.result['sync']['success'])
            self.assertEqual(self.lab.result['discovery']['active'],100)
        self.assertEqual(self.lab.result['active_after_offline'],95)
        with patch('live_lab.load_questions',return_value=[{'id':1,'question':'测试夹具题目','answer':''}]):
            self.command('answer_save',qid=1,answer='会话作答')
            self.assertEqual(self.lab.snapshot()['questions'][0]['answer'],'会话作答')
        self.assertEqual(self.lab.snapshot()['questions'],[])

    def test_teacher_question_entry_answer_and_no_source_mutation(self):
        first=self.command('question_add',question='测试夹具中的教师原题')['question_id']
        second=self.command('question_add',question='另一个测试夹具题目')['question_id']
        self.assertEqual((first,second),(1,2))
        self.command('answer_save',qid=first,answer='测试会话答案')
        rows=self.lab.snapshot()['questions']
        self.assertEqual(rows[0]['answer'],'测试会话答案')
        self.assertEqual(json.loads((Path(__file__).resolve().parents[1]/'content/coursework.json').read_text()),[])
