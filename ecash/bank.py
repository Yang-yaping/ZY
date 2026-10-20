import hashlib
import hmac
import json
import secrets
from .crypto import *
from .storage import Store

class Bank:
    def __init__(self, path):
        self.db = Store(path)
        self.db.setup('''
        CREATE TABLE IF NOT EXISTS settings(id TEXT PRIMARY KEY,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS accounts(name TEXT PRIMARY KEY,kind TEXT NOT NULL,identity TEXT UNIQUE NOT NULL,salt TEXT NOT NULL,password TEXT NOT NULL,balance INTEGER NOT NULL CHECK(balance>=0),active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS issuance(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES accounts(name),state TEXT NOT NULL,blinded TEXT NOT NULL,survivor INTEGER NOT NULL,signature TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS deposits(serial TEXT PRIMARY KEY,merchant TEXT NOT NULL,transcript TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY,serial TEXT NOT NULL,transcript TEXT NOT NULL,identity TEXT,positions TEXT NOT NULL,status TEXT NOT NULL,UNIQUE(serial,transcript));
        ''')
    def initialize(self):
        with self.db.tx() as c:
            require(not c.execute('SELECT 1 FROM settings').fetchone(), '银行密钥已存在，不可覆盖')
            pub, d = generate_key()
            c.execute('INSERT INTO settings VALUES (?,?)', ('key', canonical({'public':pub,'d':d})))
        return pub
    def key(self):
        r = self.db.rows('SELECT data FROM settings WHERE id=?', ('key',))
        require(bool(r), '请先生成银行密钥')
        return json.loads(r[0]['data'])
    @property
    def public(self):
        return self.key()['public']
    def create_account(self, name, password, kind='payer'):
        require(isinstance(name,str) and 1 <= len(name) <= 40 and name.replace('_','').isalnum(), '账户名须为1至40位字母数字或下划线')
        require(isinstance(password,str) and 8 <= len(password) <= 128, '密码须为8至128字符')
        require(kind in ('payer','merchant'), '账户类型错误')
        salt = secrets.token_bytes(32)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 200000).hex()
        with self.db.tx() as c:
            require(not c.execute('SELECT 1 FROM accounts WHERE name=?',(name,)).fetchone(), '账户已存在')
            c.execute('INSERT INTO accounts(name,kind,identity,salt,password,balance) VALUES (?,?,?,?,?,?)', (name,kind,token(),salt.hex(),digest,100 if kind=='payer' else 0))
    def auth(self, c, name, password, kind=None):
        require(isinstance(password,str) and len(password)<=128, '密码格式错误')
        a = c.execute('SELECT * FROM accounts WHERE name=?',(name,)).fetchone()
        require(a is not None, '账户或密码错误')
        digest = hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(a['salt']),200000).hex()
        require(hmac.compare_digest(digest,a['password']), '账户或密码错误')
        require(a['active']==1 and (kind is None or a['kind']==kind), '账户冻结或角色不符')
        return a
    def account(self, name, password):
        with self.db.tx() as c:
            a = self.auth(c,name,password)
            return {k:a[k] for k in ('name','kind','identity','balance','active')}
    def begin(self, owner, password, blinded):
        pub = self.public
        require(isinstance(blinded,list) and 2<=len(blinded)<=64, '候选数量须为2至64')
        for b in blinded: scalar(b,pub)
        require(len(set(blinded))==len(blinded), '禁止重复候选盲化值')
        with self.db.tx() as c:
            a = self.auth(c,owner,password,'payer')
            require(a['balance']>=10, '取款余额不足')
            previous = {v for row in c.execute('SELECT blinded FROM issuance') for v in json.loads(row['blinded'])}
            require(not previous.intersection(blinded), '候选盲化值曾提交过，禁止重用；请重新生成候选')
            # Commit immutable values before drawing unpredictable challenge within same transaction.
            rid = token()
            survivor = secrets.randbelow(len(blinded))
            c.execute('UPDATE accounts SET balance=balance-10 WHERE name=?',(owner,))
            c.execute('INSERT INTO issuance(id,owner,state,blinded,survivor) VALUES (?,?,?,?,?)',(rid,owner,'CHALLENGED',canonical(blinded),survivor))
        return rid, survivor
    def cancel(self, rid, owner, password):
        with self.db.tx() as c:
            self.auth(c,owner,password,'payer')
            r=c.execute('SELECT * FROM issuance WHERE id=? AND owner=?',(rid,owner)).fetchone()
            require(r is not None and r['state']=='CHALLENGED','该取款不能取消')
            c.execute("UPDATE issuance SET state='CANCELLED' WHERE id=?",(rid,))
            c.execute('UPDATE accounts SET balance=balance+10 WHERE name=?',(owner,))
    def issue(self, rid, owner, password, openings):
        key = self.key(); pub=key['public']
        failure=None; result=None
        with self.db.tx() as c:
            a=self.auth(c,owner,password,'payer')
            r=c.execute('SELECT * FROM issuance WHERE id=? AND owner=?',(rid,owner)).fetchone()
            require(r is not None,'无此取款或账户不符')
            if r['state']=='SIGNED': return r['signature'] # idempotent retry, never re-sign
            require(r['state']=='CHALLENGED','取款已终止')
            blinded=json.loads(r['blinded'])
            try:
                require(isinstance(openings,dict) and set(openings)=={str(i) for i in range(len(blinded)) if i!=r['survivor']},'必须且只能打开抽中的 N−1 枚')
                for i, candidate_data in openings.items():
                    check_opening(candidate_data,a['identity'],blinded[int(i)],pub)
                result=str(pow(int(blinded[r['survivor']]),int(key['d']),int(pub['n'])))
                require(pow(int(result),pub['e'],int(pub['n']))==int(blinded[r['survivor']]),'RSA 自检失败')
                c.execute("UPDATE issuance SET state='SIGNED',signature=? WHERE id=?",(result,rid))
            except ProtocolError as e:
                failure=str(e)
                c.execute("UPDATE issuance SET state='REJECTED' WHERE id=?",(rid,))
                c.execute('UPDATE accounts SET balance=balance+10 WHERE name=?',(owner,))
        if failure: raise ProtocolError(failure+'；抽查失败，余额已退还')
        return result
    def deposit(self, tr, merchant, password):
        # Fully verify before deduplication or identity extraction.
        pub=self.public
        verify_transcript(tr,pub)
        require(tr['merchant']==merchant,'凭证收款人与存款账户不符')
        serial=tr['cash']['coin']['serial']
        encoded=canonical(tr)
        with self.db.tx() as c:
            self.auth(c,merchant,password,'merchant')
            old=c.execute('SELECT * FROM deposits WHERE serial=?',(serial,)).fetchone()
            if old is None:
                c.execute('INSERT INTO deposits(serial,merchant,transcript) VALUES (?,?,?)',(serial,merchant,encoded))
                c.execute('UPDATE accounts SET balance=balance+10 WHERE name=?',(merchant,))
                return {'status':'CREDITED','identity':None,'positions':[]}
            if old['transcript']==encoded:
                return {'status':'REPLAY','identity':None,'positions':[]}
            first=json.loads(old['transcript'])
            identity, positions=recover(first,tr,pub)
            status='DOUBLE_SPEND_IDENTIFIED' if identity else 'DUPLICATE_SAME_CHALLENGE'
            c.execute('INSERT OR IGNORE INTO evidence(serial,transcript,identity,positions,status) VALUES (?,?,?,?,?)',(serial,encoded,identity,canonical(positions),status))
            return {'status':status,'identity':identity,'positions':positions}
    def dashboard(self):
        return {'accounts':self.db.rows('SELECT name,kind,balance,active FROM accounts'),
                'issuance':self.db.rows('SELECT id,owner,state,survivor,created FROM issuance'),
                'deposits':self.db.rows('SELECT serial,merchant,created FROM deposits'),
                'evidence':self.db.rows('SELECT id,serial,identity,positions,status FROM evidence')}
    def resolve_identity(self, identity):
        return self.db.rows('SELECT name FROM accounts WHERE identity=?',(identity,))

    def set_active(self, name, active):
        """Local simulator administrator control, not a remotely exposed API."""
        require(type(active) is bool, '账户开关类型错误')
        with self.db.tx() as c:
            require(c.execute('SELECT 1 FROM accounts WHERE name=?',(name,)).fetchone() is not None,'无此账户')
            c.execute('UPDATE accounts SET active=? WHERE name=?',(int(active),name))
