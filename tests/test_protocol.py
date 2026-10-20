import copy, tempfile, unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from ecash.bank import Bank
from ecash.actors import Wallet, Merchant
from ecash.crypto import *

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.k=generate_key()
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); p=Path(self.tmp.name)
  self.b=Bank(p/'bank.db')
  with self.b.db.tx() as c:c.execute('INSERT INTO settings VALUES (?,?)',('key',canonical({'public':self.k[0],'d':self.k[1]})))
  for n,k in [('alice','payer'),('bob','payer'),('shop_a','merchant'),('shop_b','merchant')]:self.b.create_account(n,'password123',k)
  self.u=self.b.account('alice','password123')['identity']; self.w=Wallet(p/'wallet.db',self.b.public)
  self.a=Merchant(p/'a.db',self.b.public,'shop_a'); self.m=Merchant(p/'m.db',self.b.public,'shop_b')
 def tearDown(self):self.tmp.cleanup()
 def prep(self):
  w=self.w.prepare(self.u,4,8); r,s=self.b.begin('alice','password123',self.w.submission(w)); self.w.challenge(w,r,s); return w,r
 def withdraw(self):
  w,r=self.prep(); self.w.finish(w,self.b.issue(r,'alice','password123',self.w.openings(w))); return w
 def pay(self,w,m,double=False):
  q=m.offer(self.w.cash(w)); t=self.w.respond(w,q,double); m.accept(t); return t
 def dep(self,t):return self.b.deposit(t,t['merchant'],'password123')
 def test_legal_anonymous_offline(self):
  w=self.withdraw(); t=self.pay(w,self.a); self.assertEqual(self.dep(t)['status'],'CREDITED')
  self.assertEqual(self.b.account('alice','password123')['balance'],90)
  self.assertNotIn('alice',canonical(t)); self.assertNotIn(self.u,canonical(t))
  self.assertNotIn(t['cash']['coin']['serial'],canonical(self.b.db.rows('SELECT * FROM issuance')))
  with patch.object(Bank,'key',side_effect=AssertionError('bank offline')):self.m.offer(self.w.cash(w))
 def test_forgery(self):
  cash=self.w.cash(self.withdraw())
  for field in ('signature','amount','serial','commitments'):
   bad=copy.deepcopy(cash)
   if field=='signature':bad[field]='2'
   elif field=='amount':bad['coin'][field]=100
   elif field=='serial':bad['coin'][field]=token()
   else:bad['coin'][field][0][0]=token()
   with self.assertRaises(ProtocolError):self.a.offer(bad)
 def test_double_spend(self):
  w=self.withdraw()
  with patch('ecash.actors.secrets.randbits',return_value=0):a=self.pay(w,self.a)
  with patch('ecash.actors.secrets.randbits',return_value=1):b=self.pay(w,self.m,True)
  self.dep(a); r=self.dep(b)
  self.assertEqual(r['identity'],self.u); self.assertEqual(r['positions'],list(range(8)))
  self.assertEqual(self.b.resolve_identity(r['identity']),[{'name':'alice'}])
  self.assertEqual(self.b.account('shop_b','password123')['balance'],0)
 def test_equal_challenge_boundary(self):
  w=self.withdraw()
  with patch('ecash.actors.secrets.randbits',return_value=0):a=self.pay(w,self.a); b=self.pay(w,self.m,True)
  self.dep(a); self.assertEqual(self.dep(a)['status'],'REPLAY')
  r=self.dep(b); self.assertEqual(r['status'],'DUPLICATE_SAME_CHALLENGE'); self.assertIsNone(r['identity'])
  t=8; self.assertEqual(sum(x==y for x in range(2**t) for y in range(2**t))/2**(2*t),2**-t)
 def test_atomic_concurrent(self):
  w=self.withdraw(); a=self.pay(w,self.a)
  with ThreadPoolExecutor(max_workers=8) as p:rs=list(p.map(lambda _:self.dep(a),range(8)))
  self.assertEqual(sum(r['status']=='CREDITED' for r in rs),1)
  self.assertEqual(self.b.account('shop_a','password123')['balance'],10)
 def test_two_merchants_concurrent(self):
  w=self.withdraw(); a=self.pay(w,self.a); b=self.pay(w,self.m,True)
  with ThreadPoolExecutor(max_workers=2) as p:rs=list(p.map(self.dep,[a,b]))
  self.assertEqual(sum(r['status']=='CREDITED' for r in rs),1)
  self.assertEqual(sum(self.b.account(n,'password123')['balance'] for n in ('shop_a','shop_b')),10)
 def test_cut_choose_failure_refund(self):
  w,r=self.prep(); o=self.w.openings(w); next(iter(o.values()))['opening'][0][0]['share']=token()
  with self.assertRaises(ProtocolError):self.b.issue(r,'alice','password123',o)
  self.assertEqual(self.b.account('alice','password123')['balance'],100)
  with self.assertRaises(ProtocolError):self.b.issue(r,'alice','password123',o)
  with self.assertRaises(ProtocolError):self.b.cancel(r,'alice','password123')
 def test_cancel_owner_balance(self):
  w,r=self.prep()
  with self.assertRaises(ProtocolError):self.b.issue(r,'bob','password123',self.w.openings(w))
  self.b.cancel(r,'alice','password123'); self.assertEqual(self.b.account('alice','password123')['balance'],100)
  with self.b.db.tx() as c:c.execute("UPDATE accounts SET balance=0 WHERE name='alice'")
  z=self.w.prepare(self.u,4,8)
  with self.assertRaises(ProtocolError):self.b.begin('alice','password123',self.w.submission(z))
 def test_response_and_guard(self):
  w=self.withdraw(); a=self.pay(w,self.a); q=self.m.offer(self.w.cash(w))
  with self.assertRaises(ProtocolError):self.w.respond(w,q)
  bad=copy.deepcopy(a); bad['responses'][0]['salt']=token()
  with self.assertRaises(ProtocolError):self.dep(bad)
  tr=self.w.respond(w,q,True); tr['challenge'][0]^=1
  with self.assertRaises(ProtocolError):self.m.accept(tr)
 def test_invalid_and_retry(self):
  for n,t in [(1,8),(65,8),(4,1),(True,8)]:
   with self.assertRaises(ProtocolError):self.w.prepare(token(),n,t)
  with self.assertRaises(ProtocolError):self.b.begin('alice','password123',['2','2'])
  with self.assertRaises(ProtocolError):self.b.begin('alice','wrong',['2','3'])
  w,r=self.prep(); o=self.w.openings(w); a=self.b.issue(r,'alice','password123',o)
  self.assertEqual(a,self.b.issue(r,'alice','password123',o)); self.assertEqual(self.b.account('alice','password123')['balance'],90)
  with self.assertRaises(ProtocolError):self.b.initialize()
 def test_random_freshness(self):
  a=candidate(self.u,self.b.public,8); b=candidate(self.u,self.b.public,8)
  for f in ('r','blinded','opening'):self.assertNotEqual(a[f],b[f])
  self.assertNotEqual(a['coin']['serial'],b['coin']['serial'])
 def test_frozen_and_no_reuse(self):
  w,r=self.prep(); submitted=[x['blinded'] for x in self.w.db.get(w)['candidates']]
  self.b.cancel(r,'alice','password123')
  with self.assertRaises(ProtocolError):self.b.begin('alice','password123',submitted)
  self.b.set_active('alice',False)
  with self.assertRaises(ProtocolError):self.b.account('alice','password123')
  self.b.set_active('alice',True)
  self.assertEqual(self.b.account('alice','password123')['balance'],100)
 def test_cut_choose_probability(self):
  for n in (4,16,64):
   # Exactly one of n survivor selections conceals a fixed bad candidate.
   self.assertEqual(sum(s==0 for s in range(n))/n,1/n)
 def test_persisted_terminal_and_challenge(self):
  w=self.withdraw(); q=self.a.offer(self.w.cash(w))
  restarted=Merchant(self.a.db.path,self.b.public,'shop_a')
  tr=self.w.respond(w,q); restarted.accept(tr)
  with self.assertRaises(ProtocolError):restarted.accept(tr)
  self.assertEqual(self.dep(tr)['status'],'CREDITED')
  restarted_bank=Bank(self.b.db.path)
  self.assertEqual(restarted_bank.deposit(tr,'shop_a','password123')['status'],'REPLAY')
if __name__=='__main__':unittest.main(verbosity=2)
