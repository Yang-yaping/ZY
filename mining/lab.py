"""Bounded, real SM3 work and SM2 signatures. No fabricated power readings."""
import hashlib
import json
import secrets
import time
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor
from gmssl import sm2


def encoded(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def digest(data):
    return hashlib.new('sm3', data).digest()


def keypair():
    order = int(sm2.default_ecc_table['n'], 16)
    private = f'{secrets.randbelow(order-2)+1:064x}'
    signer = sm2.CryptSM2(private_key=private, public_key='')
    public = signer._kg(int(private, 16), sm2.default_ecc_table['g'])
    # gmssl 3.2.2 uses lstrip('04'), which can strip genuine raw X digits.
    # Assign our fixed-width raw X||Y explicitly rather than prefix guessing.
    signer.public_key = public
    return signer, public


def sign(signer, message):
    order = int(sm2.default_ecc_table['n'], 16)
    for _ in range(8):
        # Never use gmssl's default random_hex (non-cryptographic random).
        signature = signer.sign_with_sm3(message, f'{secrets.randbelow(order-1)+1:064x}')
        if signature:
            return signature
    raise ValueError('SM2随机签名失败')


def verify(public, message, signature):
    try:
        if len(public) != 128 or len(signature) != 128:
            return False
        checker = sm2.CryptSM2(public_key='', private_key='')
        checker.public_key = public
        return bool(checker.verify_with_sm3(signature, message))
    except (ValueError, TypeError, IndexError):
        return False


def merkle(leaves):
    level = [digest(encoded(x)) for x in leaves]
    while len(level) > 1:
        if len(level) % 2: level.append(level[-1])
        level = [digest(level[i]+level[i+1]) for i in range(0,len(level),2)]
    return level[0].hex()


def valid(block):
    header = block['header']
    message = encoded(block['transaction']['body'])
    tx = block['transaction']
    return (verify(tx['public'], message, tx['signature']) and
            header['merkle'] == merkle([tx]) and
            digest(encoded(header)).hex() == block['hash'] and
            int(block['hash'],16) < (1 << (256-header['difficulty'])) and
            verify(block['miner_public'], bytes.fromhex(block['hash']), block['signature']))


def experiment(nodes=4, difficulty=12, rounds=3, repetitions=3, watts=None):
    if type(nodes) is not int or nodes not in (1,2,4,8,16): raise ValueError('节点数须为1、2、4、8、16')
    if type(difficulty) is not int or difficulty not in (8,12,16): raise ValueError('难度须为8、12、16位')
    if type(rounds) is not int or not 1<=rounds<=5: raise ValueError('区块数须为1至5')
    if type(repetitions) is not int or not 1<=repetitions<=5: raise ValueError('重复次数须为1至5')
    if watts is not None and (isinstance(watts,bool) or not isinstance(watts,(float,int)) or not 0<float(watts)<=2000):
        raise ValueError('功率须为空或外部实测的0至2000瓦')
    start=time.perf_counter(); cpu=time.process_time()
    overall_deadline=start+12
    keys=[keypair() for _ in range(nodes)]
    issuer, public=keypair()
    rows=[]; sample=None
    for repeat in range(repetitions):
        if time.perf_counter()>overall_deadline: break
        previous='0'*64
        for height in range(1,rounds+1):
            if time.perf_counter()>overall_deadline: break
            txbody={'from':public,'to':'classroom-recipient','amount':1,'nonce':secrets.token_hex(16)}
            tx={'body':txbody,'public':public,'signature':sign(issuer,encoded(txbody))}
            if not verify(public, encoded(txbody), tx['signature']): raise ValueError('交易验签失败')
            root=merkle([tx]); done=threading.Event(); deadline=min(overall_deadline,time.perf_counter()+3)
            wall0=time.perf_counter(); cpu0=time.process_time()
            barrier=threading.Barrier(nodes)
            def worker(i):
                header={'previous':previous,'height':height,'merkle':root,'difficulty':difficulty,
                        'miner':i,'salt':secrets.token_hex(16),'nonce':0}
                attempts=0; found=None
                try:
                    barrier.wait(timeout=1)
                except threading.BrokenBarrierError:
                    return {'node':i,'attempts':0,'candidate':None}
                while attempts<200000 and not done.is_set():
                    if attempts%256==0 and time.perf_counter()>deadline: break
                    header['nonce']=attempts
                    hashed=digest(encoded(header)); attempts+=1
                    if int.from_bytes(hashed,'big') < (1 << (256-difficulty)):
                        found={'header':dict(header),'hash':hashed.hex()};done.set();break
                return {'node':i,'attempts':attempts,'candidate':found}
            with ThreadPoolExecutor(max_workers=nodes) as pool:
                work=list(pool.map(worker,range(nodes)))
            winner=next((w for w in work if w['candidate']),None)
            elapsed=time.perf_counter()-wall0; cpu_s=time.process_time()-cpu0
            hashes=sum(w['attempts'] for w in work)
            if winner:
                block=winner['candidate']; block['transaction']=tx
                signer, miner_public=keys[winner['node']]
                block.update(miner_public=miner_public, signature=sign(signer,bytes.fromhex(block['hash'])))
                if not valid(block): raise ValueError('SM3工作量或SM2区块签名校验失败')
                previous=block['hash']; sample=block
            rows.append(dict(nodes=nodes,repeat=repeat+1,height=height,success=winner is not None,
                             hashes=hashes,elapsed_s=elapsed,cpu_s=cpu_s,
                             hashes_per_s=hashes/elapsed,workers=[{'node':w['node'],'attempts':w['attempts']} for w in work],
                             measured_system_w=watts, energy_j=watts*elapsed if watts is not None else None,
                             energy_basis='外部仪表平均整机功率×挖矿阶段耗时（非单节点功耗）' if watts is not None else '未接入功率仪；未测量'))
            if not winner: break
    return {'algorithm':'SM3 + SM2/SM3','model':'同机线程竞争PoW，不是多台物理矿机或比特币主网',
            'nodes':nodes,'difficulty':difficulty,'rounds':rounds,'repetitions':repetitions,
            'rows':rows,'summary':{'successes':sum(r['success'] for r in rows),'mean_hashes':statistics.mean(r['hashes'] for r in rows),
             'mean_elapsed_s':statistics.mean(r['elapsed_s'] for r in rows),'mean_cpu_s':statistics.mean(r['cpu_s'] for r in rows)},
            'sample':sample,'total_wall_s':time.perf_counter()-start,'total_cpu_s':time.process_time()-cpu,
            'boundary':'随机PoW有方差；同机节点数不等于独立算力。CPU秒不是功率。功率与能耗仅在输入外部实测整机功率时计算。'}
