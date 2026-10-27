"""Single-host teaching console; role switching is not a security boundary."""
import os
import json
from pathlib import Path
import streamlit as st
from ecash.bank import Bank
from ecash.actors import Wallet, Merchant
from ecash.crypto import ProtocolError, verify_cash
from ecash.runtime import session_root, bootstrap, DEMO_PASSWORD

# Public deployment defaults to one independent sandbox per visitor.
# Explicit ECASH_DATA selects persistent local mode; cloud_app.py forces cloud mode.
CLOUD=st.session_state.get('_cash_cloud', 'ECASH_DATA' not in os.environ)
ROOT=session_root(st.session_state) if CLOUD else Path(os.environ.get('ECASH_DATA',Path(__file__).parent/'data'))
bank=Bank(ROOT/'bank.db')
if CLOUD:
    bootstrap(bank)
st.markdown('''<style>
.stApp{background:linear-gradient(130deg,#f3f6fc,#eaf4f2);color:#153047}
h1,h2,h3{letter-spacing:-.025em} [data-testid="stSidebar"]{background:#102b3d}
[data-testid="stSidebar"] *{color:#eef7fa} .hero{padding:28px 32px;background:#15364b;border-radius:20px;color:white;margin-bottom:24px}
.hero h1{color:white;font-size:2.2rem;margin:5px 0}.hero p{color:#bce2df;margin:0}
[data-testid="stMetric"]{background:white;padding:16px;border-radius:14px;border:1px solid #dce9ee}
.stButton>button{border-radius:10px} [data-testid="stExpander"]{background:#ffffffaa;border-radius:12px}
</style>''',unsafe_allow_html=True)
st.markdown('<div class="hero"><p>CRYPTOGRAPHY / CHAPTER 01 / EXPERIMENT 16</p><h1>◈ 隐币实验室</h1><p>一次支付保留匿名 · 两份互补证据恢复身份</p></div>',unsafe_allow_html=True)
def remember_role():
    st.session_state['cash_role'] = st.session_state['_cash_role']

if '_cash_role' not in st.session_state:
    st.session_state['_cash_role'] = st.session_state.get('cash_role','总览')
role=st.sidebar.radio('实验工作台',['总览','银行','付款人','收款人','场景与验收'],
                      key='_cash_role',on_change=remember_role)
if CLOUD:
    st.sidebar.caption('在线版：每位访客独立实验；刷新或服务重启后可能重置。仅使用虚拟信息。')
    st.sidebar.write('示例账户：alice、shop_a、shop_b')
    st.sidebar.write('示例密码：' + DEMO_PASSWORD)
st.sidebar.caption('本机教学模拟器 · 固定面额 10\n\n角色切换用于观察协议，不提供生产级权限隔离。')

def run(fn):
    try:
        result=fn(); st.success('操作完成'); return True if result is None else result
    except (ProtocolError,ValueError,KeyError,TypeError) as e:
        st.error(str(e)); return None

def public():
    return bank.public

def wallet(owner):
    # Account names have already been authenticated and validated by bank.
    return Wallet(ROOT/'wallets'/f'{owner}.db',public())

def merchant(name):
    return Merchant(ROOT/'merchants'/f'{name}.db',public(),name)

def credentials(prefix,kind):
    names=[x['name'] for x in bank.dashboard()['accounts'] if x['kind']==kind]
    if not names:st.info('请先在银行创建对应角色账户。'); return None,None
    name=st.selectbox('选择账户',names,key=prefix+'name')
    password=st.text_input('账户密码',type='password',key=prefix+'password')
    return name,password

if role=='总览':
    st.subheader('把取款、离线支付与存款分开观察')
    a,b,c=st.columns(3)
    a.metric('01 银行','初始化 / 发行'); b.metric('02 付款人','盲化 / 应答'); c.metric('03 收款人','挑战 / 清算')
    st.markdown('''1. **银行**：生成 RSA 密钥，建立付款人和两家商户账户。
2. **付款人**：生成候选 → 提交盲化值 → 回应随机抽查 → 去盲入钱包。
3. **收款人**：选择钱包现金，验签后独立随机挑战。
4. **付款人**：回应挑战；**收款人**离线验证响应，稍后提交银行存款。
5. 对同一现金再向另一商户支付，观察双花证据和身份恢复。''')
    st.info('商户在交货前无法保证现金没有被花过。离线协议提供事后识别和威慑；只有银行清算时决定首次兑付。')
    st.caption('实验范围：教学盲 RSA、带盐承诺、XOR 身份分片、N−1 抽查、SQLite 原子清算。')
elif role=='银行':
    st.subheader('发行与清算中心')
    if not bank.db.rows('SELECT id FROM settings'):
        if st.button('生成 2048 位 RSA 银行密钥',type='primary'):run(bank.initialize); st.rerun()
    else:
        with st.expander('查看银行公钥（私钥不在页面展示）'):st.json(public())
    with st.expander('创建教学账户',expanded=True):
        with st.form('create'):
            name=st.text_input('账户名（字母数字或下划线）'); pw=st.text_input('初始密码（至少8字符）',type='password')
            kind=st.selectbox('类型',['payer','merchant'],format_func=lambda x:'付款人（初始100实验单位）' if x=='payer' else '商户（初始0）')
            if st.form_submit_button('创建账户'):run(lambda:bank.create_account(name,pw,kind))
    d=bank.dashboard()
    with st.expander('教学管理员：冻结 / 解冻账户'):
        if d['accounts']:
            target=st.selectbox('管理账户',[a['name'] for a in d['accounts']])
            enabled=st.checkbox('账户启用',value=True)
            if st.button('应用账户状态'):run(lambda:bank.set_active(target,enabled)); st.rerun()
    cols=st.columns(3)
    cols[0].metric('已签发取款',sum(x['state']=='SIGNED' for x in d['issuance'])); cols[1].metric('首次兑付',len(d['deposits'])); cols[2].metric('重复凭证',len(d['evidence']))
    for key,label in [('accounts','账户余额'),('issuance','发行 / 抽查状态（无最终序列号）'),('deposits','存款记录'),('evidence','双花证据')]:
        st.markdown('**'+label+'**'); st.dataframe(d[key],width='stretch')
    for e in d['evidence']:
        if e['identity']:st.warning(f"证据 {e['id']} 恢复身份：{bank.resolve_identity(e['identity'])}；不同挑战位置：{e['positions']}")
elif role=='付款人':
    st.subheader('付款人钱包')
    owner,pw=credentials('p','payer')
    if owner and pw:
        try:
            account=bank.account(owner,pw); w=wallet(owner)
            st.metric('可用实验余额',account['balance'])
            n=st.slider('候选数 N（打开 N−1 枚）',2,64,16); t=st.select_slider('挑战位数 t',[8,16,32,64,128],value=32)
            st.caption(f'单坏候选抽查逃逸：1/{n}；独立挑战完全相同概率：2⁻{t} = {2**-t:.3g}')
            if st.button('① 生成候选电子现金并盲化',type='primary'):run(lambda:w.prepare(account['identity'],n,t))
            entries=w.list()
            if entries:
                wid=st.selectbox('钱包条目',[x[0] for x in entries],format_func=lambda x:x[:12]+' · '+dict(entries)[x])
                obj=w.db.get(wid)
                if obj['state']=='CHALLENGED':
                    rows=bank.db.rows('SELECT state FROM issuance WHERE id=? AND owner=?',(obj['rid'],owner))
                    if rows and rows[0]['state'] in ('REJECTED','CANCELLED'):
                        obj['state']=rows[0]['state']; w.db.put(wid,obj)
                state=obj['state']; st.code(state,language=None)
                if state=='PREPARED':
                    if st.button('② 提交盲化值，接收银行随机抽查'):
                        def submit():
                            values=w.submission(wid)
                            pending=bank.db.rows("SELECT id,survivor FROM issuance WHERE owner=? AND blinded=? AND state='CHALLENGED'",(owner,json.dumps(values,sort_keys=True,separators=(',',':'))))
                            if pending: rid,s=pending[0]['id'],pending[0]['survivor']
                            else: rid,s=bank.begin(owner,pw,values)
                            w.challenge(wid,rid,s)
                        if run(submit): st.rerun()
                elif state=='CHALLENGED':
                    st.write(f"未打开候选索引：{obj['survivor']}；其余全部须开封验证。")
                    if st.button('③ 回应抽查 → 银行盲签 → 去盲'):
                        def finish():
                            sig=bank.issue(obj['rid'],owner,pw,w.openings(wid)); w.finish(wid,sig)
                        if run(finish): st.rerun()
                    if st.button('取消取款并退还预扣金额'):
                        def cancel():
                            bank.cancel(obj['rid'],owner,pw); obj['state']='CANCELLED'; w.db.put(wid,obj)
                        if run(cancel): st.rerun()
                elif state in ('READY','SPENT'):
                    st.write('货币序列号：'+obj['cash']['coin']['serial'])
                    st.download_button('导出公共现金（无身份分片）',json.dumps(obj['cash']),file_name='cash.json')
                    with st.expander('回应商户挑战',expanded=True):
                        offers=[]
                        for a in bank.dashboard()['accounts']:
                            if a['kind']=='merchant':
                                m=merchant(a['name'])
                                for row in m.db.rows('SELECT data FROM objects'):
                                    x=json.loads(row['data'])
                                    if x['state']=='CHALLENGED' and x['request']['cash']==obj['cash']:offers.append(x['request'])
                        if offers:
                            q=st.selectbox('待回应挑战',offers,format_func=lambda x:x['merchant']+' · '+x['payment_id'][:10])
                            st.write('挑战向量：'+''.join(map(str,q['challenge'])))
                            double=st.checkbox('显式开启双花攻击演示（会泄露互补分片）')
                            if st.button('④ 生成挑战响应'):
                                tr=run(lambda:w.respond(wid,q,double))
                                if tr:st.session_state['response:'+q['payment_id']]=tr
                        else:st.info('请到收款人页面选择这枚现金并发起随机挑战。')
        except ProtocolError as e:st.error(str(e))
elif role=='收款人':
    st.subheader('商户离线验收终端')
    name,pw=credentials('m','merchant')
    if name and pw:
        try:
            bank.account(name,pw); m=merchant(name)
            st.caption('账户认证和公钥加载属于模拟器入口；offer / accept 两个协议方法只使用本地公钥和凭证，不查询银行。')
            choices=[]
            for a in bank.dashboard()['accounts']:
                if a['kind']=='payer':
                    w=wallet(a['name'])
                    for wid,state in w.list():
                        if state in ('READY','SPENT'):choices.append((a['name'],wid,w.cash(wid)))
            if choices:
                x=st.selectbox('演示传递：选择付款人送来的公共现金',choices,format_func=lambda x:x[0]+' / '+x[1][:12])
                if st.button('① 验银行签名并产生独立随机挑战',type='primary'):
                    q=run(lambda:m.offer(x[2]))
                    if q:st.success('挑战已生成，请切换付款人回应。')
            uploaded=st.file_uploader('也可导入公共现金 JSON（最大100KB）',type='json')
            if uploaded and st.button('导入验签并挑战'):
                def import_cash():
                    if uploaded.size>100000:raise ProtocolError('文件过大')
                    return m.offer(json.loads(uploaded.getvalue()))
                run(import_cash)
            for row in m.db.rows('SELECT * FROM objects'):
                obj=json.loads(row['data']); pid=row['id']
                with st.expander(pid[:12]+' · '+obj['state'],expanded=obj['state']!='DEPOSITED'):
                    st.write('随机挑战：'+''.join(map(str,obj['request']['challenge'])))
                    tr=st.session_state.get('response:'+pid)
                    if obj['state']=='CHALLENGED':
                        if tr:
                            if st.button('② 离线验证响应并验收',key='accept'+pid):
                                if run(lambda:m.accept(tr)): st.rerun()
                        else:st.info('等待付款人回应挑战。')
                    if 'transcript' in obj:
                        st.download_button('导出支付凭证',json.dumps(obj['transcript']),file_name='transcript.json',key='download'+pid)
                        if st.button('③ 提交银行存款',key='deposit'+pid):
                            r=run(lambda:bank.deposit(obj['transcript'],name,pw))
                            if r:m.mark_deposit(pid,r); st.json(r)
                        if obj.get('result'):st.json(obj['result'])
        except ProtocolError as e:st.error(str(e))
else:
    st.subheader('可重复验收场景')
    st.markdown('''| 场景 | 操作与预期 |
|---|---|
| 正常支付 | 取款一次、商户挑战验收、存款，付款人−10、商户+10 |
| 伪造签名 | 修改导出 cash.json 的 signature 或 amount，导入时拒绝 |
| 双花身份恢复 | 同一现金向两商户支付，明确开启攻击开关；两者离线验收，银行只兑付一次，挑战不同即恢复身份 |
| 相同挑战 | 自动化测试在随机源边界注入相同位；拒绝第二次兑付但无法恢复身份 |
| 并发存款 | 自动测试8线程同时提交，只入账一次 |
| 抽查作弊 | 自动测试修改开封分片，拒签、退余额且请求终止 |
''')
    st.code('python -m unittest discover -s tests -v',language='bash')
    st.info('边界测试只在测试中替换随机源。正式页面始终使用 secrets，不提供手动挑战或固定随机种子。')
    st.caption('侧栏可切换到 P2P 网络与区块同步实验；原始协议测试位于 tests/。')
