"""Coursework dashboard. Run with: streamlit run app.py"""
import asyncio
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from lab.blocks import make_chain
from lab.demo import demonstration
from lab.network import LABELS
from lab.storage import load_chain

ROOT = Path(__file__).resolve().parent
if __name__ == '__main__':
    st.set_page_config(page_title='隐币实验室 · P2P',page_icon='🔗',layout='wide')
st.markdown('''<style>
.stApp{background:#f3f6fb} .block-container{max-width:1280px;padding-top:2.2rem}
[data-testid="stMetric"]{background:white;border:1px solid #dde5f0;border-radius:16px;padding:18px}
[data-testid="stSidebar"]{background:#102b3d}
[data-testid="stSidebar"] *{color:#eef7fa} h1,h2,h3{color:#152b4c}
.hero{background:linear-gradient(120deg,#142d50,#245484);border-radius:22px;padding:30px 34px;
color:white;margin-bottom:22px}.hero h1{color:white;font-size:2rem;margin:4px 0 10px}
.eyebrow{font-size:12px;letter-spacing:3px;color:#b4d9f8}.hero p{color:#deebfa;margin:0;line-height:1.9}
.note{color:#536883;font-size:13px;padding:12px 0}
</style>''',unsafe_allow_html=True)
st.markdown('''<div class="hero"><div class="eyebrow">隐币实验室 / DISTRIBUTED SYSTEMS</div>
<h1>P2P 网络与区块同步实验室</h1><p>100 个已有节点，1 个新节点。观察发现、同步、故障恢复与密码学校验的全过程。</p>
<p>本机 TCP 实际传输 ｜ Bitcoin Script P2PKH ｜ SHA-256 & Merkle Tree</p></div>''',unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def chain_for(size):
    folder = ROOT/'results'/'fixtures'/str(size)
    return load_chain(folder) if (folder/'public.json').exists() else make_chain(size,10)


def read_csv(name):
    path = ROOT/'results'/name
    return pd.read_csv(path) if path.exists() else None


with st.sidebar:
    st.subheader('🔗 P2P 实验指南')
    st.caption('作业一 · P2P 网络与区块同步')
    st.markdown('**操作步骤**\n\n1. 选择实验参数。\n2. 点击开始实验。\n3. 查看节点、校验和数据。')
    st.divider()
    st.markdown('**实验规模**\n\n100 个已有节点 + 1 个新节点\n\n每个区块 4 笔签名交易')
    st.info('这是课程教学模拟。带宽、延迟和故障由应用层注入；耗时由实际运行计时。')
    st.caption('无真实资产 · 无挖矿或共识 · 无主网连接')

tabs = st.tabs(['▶ 实验控制台','◉ 活跃节点','✓ 密码学校验','▤ 批量实测','↗ 提交与说明'])
result = st.session_state.get('p2p_result')
with tabs[0]:
    st.subheader('配置一次同步实验')
    c1,c2,c3,c4 = st.columns(4)
    size = c1.selectbox('每个区块的传输大小',[65536,262144,1048576],index=1,
                        format_func=lambda x:f'{x//1024} KiB')
    count = c2.selectbox('新节点需要同步的区块数',[1,2,3,10],index=2)
    profile = c3.selectbox('网络条件',list(LABELS),format_func=lambda x:LABELS[x])
    optimized = c4.selectbox('同步策略',[True,False],format_func=lambda x:'多源并发＋断点续传' if x else '单路顺序＋整块重传')
    workers = st.slider('优化方案并行下载数',1,8,4,disabled=not optimized)
    st.caption('两种策略使用同样的 4 个已发现提供者；顺序基线也能在失败后切换节点。每次运行会建立并关闭独立的 101 个本机 TCP 监听端口。')
    if st.button('开始实验',type='primary',width='stretch'):
        with st.spinner('正在建立节点、发现邻居、传输区块并执行脚本校验…'):
            try:
                result = asyncio.run(demonstration(chain_for(size),count,profile,optimized,workers))
                st.session_state.p2p_result = result
                st.session_state.pop('p2p_run_error',None)
            except Exception as exc:
                st.session_state.p2p_run_error = f'{type(exc).__name__}: {exc}'
                result = None
                st.session_state.pop('p2p_result',None)
    if 'p2p_run_error' in st.session_state:
        st.error('本次实验未完成：'+st.session_state.p2p_run_error)
    if result:
        r = result['sync']
        st.success(f"同步完成 · {LABELS[result['profile']]} · {result['strategy']} · 全部校验通过")
        cols = st.columns(4)
        cols[0].metric('发现活跃节点',result['discovery']['active'])
        cols[1].metric('新节点区块高度',r['height'])
        cols[2].metric('同步总耗时',f"{r['elapsed_s']*1000:.1f} ms")
        cols[3].metric('有效吞吐量',f"{r['throughput_mib_s']:.2f} MiB/s")
        st.markdown('**状态流程**')
        for state in result['states']:
            st.write('✓ '+state)
        details = pd.DataFrame([
            ['下载阶段',f"{r['download_s']*1000:.2f} ms"],['密码学与状态校验',f"{r['validation_s']*1000:.2f} ms"],
            ['有效区块字节',r['good_bytes']],['接收的区块数据字节（含重传）',r['received_bytes']],
            ['传输效率',f"{100*r['transfer_efficiency']:.1f}%"],['数据排队 P95',f"{r['queue_p95_ms']:.2f} ms"],
            ['重试次数',r['retries']],['BUSY 拒绝次数',r['busy']],['超时次数',r['timeouts']]],columns=['指标','本次实测'])
        details['本次实测'] = details['本次实测'].astype(str)
        st.dataframe(details,width='stretch',hide_index=True)
        if result['events']:
            with st.expander('故障与重试记录'):
                st.json(result['events'])
        st.download_button('下载本次实验 JSON',json.dumps(result,ensure_ascii=False,indent=2),
                           'single_run.json','application/json')
    else:
        st.info('点击“开始实验”生成本次运行数据。下方批量实测页面可查看已交付的原始实验结果。')

with tabs[1]:
    st.subheader('节点加入、发现与列表维护')
    st.write('新节点只知道 3 个种子地址，通过 HELLO 交换邻居列表，再逐个探测验证。活跃表记录地址、最近响应时间、响应耗时和连续失败次数；30 秒过期，两轮心跳失败后标记不活跃。')
    st.code('新节点加入 → 种子握手 → 邻居传播 → 主动验证 → 活跃表\n                                              ↓\n                           周期心跳 / TTL → 失活标记 → 重新发现',language=None)
    if result:
        c1,c2,c3 = st.columns(3)
        c1.metric('实际监听节点',result['listeners'])
        c2.metric('发现耗时',f"{result['discovery']['elapsed_s']*1000:.1f} ms")
        c3.metric('关闭 5 个节点并维护后',result['active_after_offline'])
        st.caption('下表来自本次运行：关闭节点 0～4，连续执行两轮心跳。端口由操作系统自动分配，每次会变化。')
        df = pd.DataFrame(result['after_offline']).rename(columns={'id':'节点编号','port':'本机端口',
                    'failures':'连续失败','rtt_ms':'最近探测耗时 ms','active':'活跃'})
        st.dataframe(df,width='stretch',hide_index=True)
    else:
        st.info('先在实验控制台运行一次，可查看真实的 100 行节点列表。')

with tabs[2]:
    st.subheader('真实 Bitcoin Script 字节码与验签')
    st.write('每笔交易花费一个已知 UTXO。解锁脚本压入签名和公钥，锁定脚本检查公钥哈希并执行 OP_CHECKSIG。签名使用 secp256k1 ECDSA，签名摘要按 Bitcoin 旧式交易的 SIGHASH_ALL 规则生成。')
    st.code('scriptSig:    <DER ECDSA signature + 01> <compressed public key>\nscriptPubKey: OP_DUP OP_HASH160 <20-byte pubkey hash> OP_EQUALVERIFY OP_CHECKSIG',language=None)
    sample = result['sample'] if result else chain_for(65536).sample
    with st.expander('查看实际交易的脚本字节',expanded=True):
        st.caption('以下数据来自公开实验夹具；没有导出私钥。')
        st.text('锁定脚本 HEX')
        st.code(sample['locking_hex'],language=None)
        st.text('解锁脚本 HEX')
        st.code(sample['unlocking_hex'],language=None)
    st.markdown('**区块接收校验顺序**\n\n1. 长度与区块传输校验和。\n2. 可信检查点、前区块哈希和高度。\n3. 交易 Merkle 根与填充数据哈希。\n4. UTXO 存在且未重复花费、真实脚本执行、金额守恒。\n5. 整块通过后原子更新本地 UTXO 状态。')
    st.warning('教学区块采用自定义封装，不是比特币主网区块。只支持旧式 P2PKH 子集，不包含完整比特币共识规则。区块大小通过已认证的填充数据调整，交易数固定为 4 笔，因此不能据此推断真实链的交易验证扩展性。')
    if result:
        st.dataframe(pd.DataFrame(result['manifest']),width='stretch',hide_index=True)

with tabs[3]:
    st.subheader('可追溯的批量实测结果')
    path = ROOT/'results'/'metadata.json'
    meta = json.loads(path.read_text()) if path.exists() else {}
    df = read_csv('sync_raw.csv')
    if df is not None and not df.empty:
        a,b,c = st.columns(3)
        a.metric('同步测量次数',len(df))
        b.metric('同步成功次数',int(df['success'].sum()))
        c.metric('每组重复次数',meta.get('repetitions','—'))
        st.caption('同一组公开区块夹具、同一拓扑和同一组提供者；每次清空下载状态。实验顺序由固定种子打乱，每组展示均值。数据仅代表本机及指定应用层网络模型。')
        x,y = st.columns(2)
        selected_profile = x.selectbox('查看网络条件',list(LABELS),format_func=lambda p:LABELS[p],key='p2p_result_profile')
        selected_size = y.selectbox('查看区块大小',sorted(df.block_bytes.unique()),format_func=lambda s:f'{s//1024} KiB',key='p2p_result_size')
        sub = df[(df.profile==selected_profile)&(df.block_bytes==selected_size)]
        agg = sub.groupby(['blocks','strategy'],as_index=False).agg(elapsed_s=('elapsed_s','mean'),std_s=('elapsed_s','std'),
                         efficiency=('transfer_efficiency','mean'),queue_p95_ms=('queue_p95_ms','mean'))
        st.line_chart(agg.pivot(index='blocks',columns='strategy',values='elapsed_s'),x_label='同步区块数',y_label='平均总耗时（秒）')
        st.dataframe(agg.rename(columns={'blocks':'区块数','strategy':'策略','elapsed_s':'平均秒','std_s':'标准差秒',
                                        'efficiency':'传输效率','queue_p95_ms':'排队P95毫秒'}),hide_index=True,width='stretch')
        with st.expander('并发负载实验：4 个同步会话竞争 1 个提供者'):
            load = read_csv('load_raw.csv')
            if load is not None:
                st.dataframe(load,width='stretch',hide_index=True)
        for name,label in [('sync_raw.csv','下载同步原始数据'),('discovery_raw.csv','下载节点发现数据'),('load_raw.csv','下载并发负载数据')]:
            file = ROOT/'results'/name
            if file.exists():
                st.download_button(label,file.read_bytes(),name,'text/csv',key=name)
        st.caption(f"测量开始时间（UTC）：{meta.get('started_utc','记录中')}。baseline = 顺序基线；optimized = 多源并发与断点续传。")
    else:
        st.info('尚无批量数据。请按 README 运行 tools/run_experiments.py，完成后刷新页面。')

with tabs[4]:
    st.subheader('作业交付内容')
    st.markdown('''- **源代码**：`app.py`、`lab/`、`tools/`、`tests/`。
- **实验数据**：`results/` 中的原始 CSV、环境信息、故障日志与公开区块夹具。
- **设计说明**：`docs/` 中的模块设计与演示步骤。
- **运行方法**：先安装 `requirements.txt`，再运行 `streamlit run app.py`。
''')
    st.write('传输使用 TCP：提供可靠、有序的字节流，适合区块完整传输。程序增加长度前缀处理消息边界，并通过应用层校验、重试与断点续传处理完整性和连接失败。TCP 不保证节点诚实，也不能解决离线节点或无限并发。')
    st.info('设计说明列出了建议演示步骤。需要截图时请从实际运行页面拍摄。')
    st.caption('参考：RFC 9293；Bitcoin Developer Guide；python-bitcoinlib。详细链接和安全边界见 README。')
st.markdown('<div class="note">课程实验 · P2P 与区块同步 · 计时来自实际执行，网络条件来自明确的教学模型</div>',unsafe_allow_html=True)
