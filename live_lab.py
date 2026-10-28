"""Session-scoped adapter for the interactive design, using the existing cores.

Only explicit, validated commands are accepted. Snapshots never contain bank
private keys, password hashes, identity shares, or wallet blinding factors.
"""
import asyncio
import copy
import json
import sqlite3
import csv
import statistics
from pathlib import Path

from ecash.actors import Wallet, Merchant
from ecash.bank import Bank
from ecash.crypto import ProtocolError, require, integer, canonical, verify_cash
from ecash.runtime import bootstrap
from coursework import load_questions

ROOT = Path(__file__).resolve().parent


class LiveLab:
    def __init__(self, root):
        self.root = Path(root)
        self.bank = Bank(self.root/'bank.db')
        bootstrap(self.bank)
        self.responses = {}
        self.answers = {}
        self.extra_questions = []
        self.result = None
        self.notice = None
        self.seen = {}
        self.revision = 0
        self.bench = self.load_bench()

    @staticmethod
    def load_bench():
        path = ROOT/'p2p/results/sync_raw.csv'
        if not path.exists():
            return {'count': 0, 'rows': []}
        with path.open(encoding='utf-8-sig') as source:
            records = list(csv.DictReader(source))
        groups = {}
        for r in records:
            if r['success'] not in ('True', 'true', '1'):
                continue
            key = (r['profile'], int(r['block_bytes']), int(r['blocks']), r['strategy'])
            groups.setdefault(key, []).append(r)
        rows = []
        for (profile, size, blocks, strategy), items in groups.items():
            times = [float(i['elapsed_s']) for i in items]
            rows.append(dict(profile=profile, size=size, blocks=blocks, strategy=strategy,
                             elapsed=statistics.mean(times), std=statistics.stdev(times) if len(times)>1 else 0,
                             efficiency=statistics.mean(float(i['transfer_efficiency']) for i in items),
                             queue=statistics.mean(float(i['queue_p95_ms']) for i in items)))
        metadata = ROOT/'p2p/results/metadata.json'
        return {'count':len(records), 'rows':rows,
                'started':json.loads(metadata.read_text()).get('started_utc','') if metadata.exists() else ''}

    def wallet(self, owner):
        self.check_name(owner, 'payer')
        return Wallet(self.root/'wallets'/f'{owner}.db', self.bank.public)

    def merchant(self, name):
        self.check_name(name, 'merchant')
        return Merchant(self.root/'merchants'/f'{name}.db', self.bank.public, name)

    def check_name(self, name, kind=None):
        require(isinstance(name, str) and 1 <= len(name) <= 40, '账户名格式错误')
        rows = self.bank.db.rows('SELECT kind FROM accounts WHERE name=?', (name,))
        require(rows and (kind is None or rows[0]['kind'] == kind), '账户不存在或角色不符')

    def account(self, p, kind):
        self.check_name(p.get('name'), kind)
        return self.bank.account(p['name'], p.get('password'))

    def handle(self, event):
        """Replay protection spans reruns; failure acknowledgements are cached too."""
        try:
            require(isinstance(event, dict) and set(event) == {'id', 'action', 'payload'}, '操作格式错误')
            eid = event['id']
            require(isinstance(eid, str) and 8 <= len(eid) <= 80, '操作编号错误')
            require(isinstance(event['payload'], dict) and len(canonical(event)) <= 180000, '操作内容过大或格式错误')
            if eid in self.seen:
                self.notice = self.seen[eid]
                return self.notice
            detail = self.execute(event['action'], event['payload'])
            notice = {'id': eid, 'ok': True, **detail}
        except (ProtocolError, ValueError, TypeError, KeyError, OSError, sqlite3.Error) as exc:
            notice = {'id': event.get('id') if isinstance(event, dict) else None,
                      'ok': False, 'message': str(exc)[:400]}
        self.revision += 1
        self.notice = notice
        if isinstance(event, dict) and isinstance(event.get('id'), str):
            self.seen[event['id']] = notice
            while len(self.seen) > 512:
                self.seen.pop(next(iter(self.seen)))
        return notice

    def execute(self, action, p):
        if action == 'refresh':
            return {'message': '已读取当前实验状态'}
        if action == 'account_create':
            self.bank.create_account(p.get('name'), p.get('password'), p.get('kind'))
            return {'message': '教学账户已创建'}
        if action == 'account_active':
            self.check_name(p.get('name'))
            self.bank.set_active(p['name'], p.get('active'))
            return {'message': '账户状态已更新'}
        if action in ('prepare', 'submit', 'issue', 'cancel', 'respond'):
            account = self.account(p, 'payer')
            w = self.wallet(p['name'])
            if action == 'prepare':
                wid = w.prepare(account['identity'], integer(p.get('n'), 2, 64), integer(p.get('t'), 8, 128))
                return {'message': '候选电子现金已生成并盲化；尚未扣款', 'wallet_id': wid}
            wid = p.get('wid')
            require(isinstance(wid, str) and len(wid) == 64, '钱包编号错误')
            obj = w.db.get(wid)
            require(obj is not None, '钱包条目不存在')
            if action == 'submit':
                values = w.submission(wid)
                pending = self.bank.db.rows("SELECT id,survivor FROM issuance WHERE owner=? AND blinded=? AND state='CHALLENGED'",
                                            (p['name'], canonical(values)))
                rid, survivor = ((pending[0]['id'], pending[0]['survivor']) if pending else
                                 self.bank.begin(p['name'], p['password'], values))
                w.challenge(wid, rid, survivor)
                return {'message': f'已预扣10实验单位；保留索引 {survivor}，其余候选须开封'}
            if action == 'issue':
                signature = self.bank.issue(obj['rid'], p['name'], p['password'], w.openings(wid))
                w.finish(wid, signature)
                return {'message': 'N−1 抽查通过；银行盲签与去盲验签完成，现金已入钱包'}
            if action == 'cancel':
                self.bank.cancel(obj['rid'], p['name'], p['password'])
                obj['state'] = 'CANCELLED'; w.db.put(wid, obj)
                return {'message': '取款已取消，10实验单位已退还'}
            require(type(p.get('double', False)) is bool, '双花开关格式错误')
            m = self.merchant(p.get('merchant'))
            payment = m.db.get(p.get('pid'))
            require(payment is not None and payment['state'] == 'CHALLENGED', '无可回应的商户挑战')
            self.responses[p['pid']] = w.respond(wid, payment['request'], p.get('double', False))
            return {'message': '已生成挑战响应；等待商户离线验证'}
        if action in ('offer', 'accept', 'deposit', 'import_cash', 'verify_forgery'):
            self.account(p, 'merchant')
            m = self.merchant(p['name'])
            if action in ('offer', 'verify_forgery'):
                cash = self.wallet(p.get('owner')).cash(p.get('wid'))
                if action == 'verify_forgery':
                    bad = copy.deepcopy(cash); bad['signature'] = str(int(bad['signature']) + 1)
                    try:
                        verify_cash(bad, self.bank.public)
                    except ProtocolError as exc:
                        return {'message': '伪造签名被正确拒绝：' + str(exc), 'verification': 'REJECTED'}
                    raise ProtocolError('伪造签名未被拒绝，请停止使用并检查协议')
                request = m.offer(cash)
                return {'message': '银行签名有效，商户已独立随机生成挑战；未查询银行存款表', 'payment_id': request['payment_id']}
            if action == 'import_cash':
                text = p.get('cash')
                require(isinstance(text, str) and len(text.encode()) <= 100000, '公共现金 JSON 最大100KB')
                q = m.offer(json.loads(text))
                return {'message': '导入现金验签成功，随机挑战已生成', 'payment_id': q['payment_id']}
            pid = p.get('pid')
            require(isinstance(pid, str) and len(pid) == 64, '支付编号错误')
            obj = m.db.get(pid)
            require(obj is not None, '商户支付条目不存在')
            if action == 'accept':
                require(pid in self.responses, '请先由付款人回应挑战')
                m.accept(self.responses[pid])
                return {'message': '响应与承诺验证通过，商户已离线验收；尚未提交存款'}
            require('transcript' in obj, '须先离线验收')
            result = self.bank.deposit(obj['transcript'], p['name'], p['password'])
            m.mark_deposit(pid, result)
            messages = {'CREDITED': '首次存款成功，商户余额增加10', 'REPLAY': '同一凭证重放，未重复入账',
                        'DOUBLE_SPEND_IDENTIFIED': '拒绝双花兑付，已恢复双花者身份',
                        'DUPLICATE_SAME_CHALLENGE': '拒绝重复兑付；两份挑战相同，无法恢复身份'}
            return {'message': messages[result['status']], 'deposit': result}
        if action == 'p2p_run':
            from p2p.lab.network import LABELS
            from p2p.lab.demo import demonstration
            from p2p.lab.storage import load_chain
            size, count, profile = p.get('size'), p.get('count'), p.get('profile')
            require(type(size) is int and size in (65536, 262144, 1048576), '区块大小错误')
            require(type(count) is int and count in (1, 2, 3, 10), '同步数量错误')
            require(isinstance(profile, str) and profile in LABELS, '网络条件错误')
            require(type(p.get('optimized')) is bool, '策略格式错误')
            workers = integer(p.get('workers'), 1, 8)
            try:
                self.result = asyncio.run(demonstration(load_chain(ROOT/'p2p/results/fixtures'/str(size)),
                                                       count, profile, p['optimized'], workers))
            except Exception as exc:
                self.result = None
                raise ProtocolError(f'本次网络实验失败：{type(exc).__name__}: {exc}') from exc
            return {'message': f"同步完成：高度 {self.result['sync']['height']}，所有密码学校验通过"}
        if action == 'question_add':
            text = p.get('question')
            require(isinstance(text, str) and 0 < len(text.strip()) <= 20000, '老师题目须为1至20000字符')
            questions = self.questions()
            qid = max((q['id'] for q in questions), default=0)+1
            require(qid <= 999, '题目编号已达999')
            self.extra_questions.append({'id':qid, 'question':text.strip(), 'answer':''})
            return {'message':f'已录入老师题目：问题{qid:03d}，可在右侧直接作答', 'question_id':qid}
        if action == 'answer_save':
            questions = self.questions()
            qid = p.get('qid'); answer = p.get('answer')
            require(type(qid) is int and any(q['id'] == qid for q in questions), '老师题目不存在')
            require(isinstance(answer, str) and len(answer) <= 100000, '答案最多100000字符')
            self.answers[qid] = answer
            return {'message': f'问题{qid:03d}答案已保存在当前会话，请下载留存'}
        raise ProtocolError('不支持的操作')

    def questions(self):
        questions = load_questions()
        ids = {q['id'] for q in questions}
        questions += [dict(q) for q in self.extra_questions if q['id'] not in ids]
        return sorted(questions, key=lambda q:q['id'])

    def snapshot(self):
        dashboard = self.bank.dashboard()
        for e in dashboard['evidence']:
            e['names'] = [row['name'] for row in self.bank.resolve_identity(e['identity'])] if e['identity'] else []
        wallets, payments = {}, {}
        for a in dashboard['accounts']:
            name = a['name']
            if a['kind'] == 'payer':
                w = self.wallet(name); wallets[name] = []
                for wid, _ in w.list():
                    obj = w.db.get(wid)
                    if obj['state'] == 'CHALLENGED':
                        rows = self.bank.db.rows('SELECT state FROM issuance WHERE id=?', (obj['rid'],))
                        if rows and rows[0]['state'] in ('REJECTED', 'CANCELLED'):
                            obj['state'] = rows[0]['state']; w.db.put(wid, obj)
                    item = {'id': wid, 'state': obj['state']}
                    if 'candidates' in obj:
                        item.update(n=len(obj['candidates']), t=obj['candidates'][0]['coin']['t'],
                                    survivor=obj.get('survivor'))
                    if 'cash' in obj:
                        item['cash'] = obj['cash']
                    wallets[name].append(item)
            else:
                m = self.merchant(name); payments[name] = []
                for row in m.db.rows('SELECT id,data FROM objects'):
                    obj = json.loads(row['data'])
                    payments[name].append({'id': row['id'], 'state': obj['state'], 'request': obj['request'],
                                           'has_response': row['id'] in self.responses,
                                           'transcript': obj.get('transcript'), 'result': obj.get('result')})
        questions = self.questions()
        for q in questions:
            q['answer'] = self.answers.get(q['id'], q.get('answer', ''))
        return {'revision': self.revision, 'notice': self.notice, 'bank': dashboard, 'public': self.bank.public,
                'wallets': wallets, 'payments': payments, 'p2p': self.result, 'questions': questions, 'bench':self.bench}
