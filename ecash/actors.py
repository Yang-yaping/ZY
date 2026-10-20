"""Payer wallet and merchant terminal. Merchant has NO Bank dependency."""
import copy
import json
import secrets
from .crypto import *
from .storage import Store

class Wallet:
    def __init__(self,path,public):
        self.db=Store(path); self.public=public
        self.db.setup('CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY,data TEXT NOT NULL);')
    def prepare(self,identity,n=16,t=32):
        integer(n,2,64)
        cs=[candidate(identity,self.public,t) for _ in range(n)]
        wid=token()
        self.db.put(wid,{'state':'PREPARED','candidates':cs})
        return wid
    def submission(self,wid):
        w=self.db.get(wid); require(w is not None and w['state']=='PREPARED','候选状态错误')
        return [c['blinded'] for c in w['candidates']]
    def challenge(self,wid,rid,survivor):
        w=self.db.get(wid); require(w is not None and w['state']=='PREPARED','不能重新抽查')
        integer(survivor,0,len(w['candidates'])-1)
        w.update(state='CHALLENGED',rid=rid,survivor=survivor)
        self.db.put(wid,w)
    def openings(self,wid):
        w=self.db.get(wid); require(w is not None and w['state']=='CHALLENGED','尚未收到抽查')
        return {str(i):c for i,c in enumerate(w['candidates']) if i!=w['survivor']}
    def finish(self,wid,signature):
        w=self.db.get(wid); require(w is not None and w['state']=='CHALLENGED','钱包状态错误')
        c=w['candidates'][w['survivor']]
        cash=unblind(c,signature,self.public)
        # Erase opened candidates and blinding factors from logical wallet record.
        self.db.put(wid,{'state':'READY','cash':cash,'opening':c['opening'],'disclosures':[]})
        return cash
    def cash(self,wid):
        w=self.db.get(wid); require(w is not None and w['state'] in ('READY','SPENT'),'货币尚未去盲')
        return copy.deepcopy(w['cash'])
    def respond(self,wid,request,allow_double_spend=False):
        with self.db.tx() as db:
            row=db.execute('SELECT data FROM objects WHERE id=?',(wid,)).fetchone()
            require(row is not None,'钱包不存在')
            w=json.loads(row['data'])
            require(w['state'] in ('READY','SPENT'),'钱包不可支付')
            require(isinstance(request,dict) and set(request)=={'payment_id','merchant','cash','challenge'},'挑战请求结构错误')
            require(request['cash']==w['cash'],'挑战不是针对本货币')
            require(isinstance(request['challenge'],list) and len(request['challenge'])==w['cash']['coin']['t'],'挑战长度错误')
            for bit in request['challenge']: integer(bit,0,1)
            same=any(x==request for x in w['disclosures'])
            require(w['state']=='READY' or same or allow_double_spend,'钱包阻止重复支付；双花演示需明确开启')
            tr=copy.deepcopy(request)
            tr['responses']=[w['opening'][i][bit] for i,bit in enumerate(request['challenge'])]
            verify_transcript(tr,self.public)
            if not same: w['disclosures'].append(copy.deepcopy(request))
            w['state']='SPENT'
            db.execute('UPDATE objects SET data=? WHERE id=?',(canonical(w),wid))
            return tr
    def list(self):
        return [(r['id'],json.loads(r['data'])['state']) for r in self.db.rows('SELECT * FROM objects')]

class Merchant:
    def __init__(self,path,public,name):
        self.db=Store(path); self.public=public; self.name=name
        self.db.setup('CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY,data TEXT NOT NULL);')
    def offer(self,cash):
        verify_cash(cash,self.public)
        pid=token()
        request={'payment_id':pid,'merchant':self.name,'cash':copy.deepcopy(cash),
                 'challenge':[secrets.randbits(1) for _ in range(cash['coin']['t'])]}
        self.db.put(pid,{'state':'CHALLENGED','request':request})
        return request
    def accept(self,tr):
        verify_transcript(tr,self.public)
        with self.db.tx() as c:
            row=c.execute('SELECT data FROM objects WHERE id=?',(tr['payment_id'],)).fetchone()
            require(row is not None,'商户没有生成此挑战')
            old=json.loads(row['data'])
            require(old['state']=='CHALLENGED','该挑战已使用')
            require(old['request']=={k:tr[k] for k in old['request']},'商户挑战已被篡改')
            c.execute('UPDATE objects SET data=? WHERE id=?',(canonical({'state':'ACCEPTED','request':old['request'],'transcript':tr}),tr['payment_id']))
        return True
    def receipts(self):
        return [json.loads(r['data']) for r in self.db.rows('SELECT * FROM objects') if json.loads(r['data'])['state']!='CHALLENGED']
    def mark_deposit(self,pid,result):
        w=self.db.get(pid); require(w is not None and 'transcript' in w,'尚未验收')
        w.update(state='DEPOSITED' if result['status'] in ('CREDITED','REPLAY') else 'DUPLICATE',result=result)
        self.db.put(pid,w)
