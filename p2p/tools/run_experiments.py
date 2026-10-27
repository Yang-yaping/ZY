"""Run actual TCP experiments. No synthetic wall-clock results are generated."""
import argparse
import asyncio
import csv
import hashlib
import importlib.metadata
import json
import platform
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.blocks import make_chain
from lab.network import Network, SyncClient, discover, maintain, percentile, PROFILES
from lab.storage import load_chain, save_chain


def write_csv(path, rows):
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def json_write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


async def run(args):
    out = ROOT/args.output
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    metadata = {'started_utc':datetime.now(timezone.utc).isoformat(), 'python':sys.version,
                'platform':platform.platform(), 'processor':platform.processor(),
                'packages':{x:importlib.metadata.version(x) for x in ['python-bitcoinlib','streamlit','matplotlib']},
                'repetitions':args.repetitions, 'topology_seed':args.seed,
                'initial_nodes':100, 'joined_nodes':1, 'profiles':PROFILES,
                'sizes_bytes':[65536,262144,1048576], 'sync_counts':[1,2,3,10],
                'transport':'real TCP on 127.0.0.1; application-layer delay/shared FIFO shaping',
                'private_keys_exported':False,
                'source_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted((ROOT/'lab').glob('*.py'))}}
    json_write(out/'metadata.json', metadata)
    chains = {}
    for size in metadata['sizes_bytes']:
        folder = out/'fixtures'/str(size)
        if (folder/'public.json').exists() and not args.fresh:
            chains[size] = load_chain(folder)
        else:
            chains[size] = make_chain(size, 10, args.seed)
            save_chain(chains[size], folder)
    sync_rows, discovery_rows, load_rows, event_rows = [], [], [], []
    async with Network(chains[65536], seed=args.seed) as net:
        origin = await net.add_node(100)
        seeds = [net.nodes[i].address for i in (0,33,66)]
        # No global address oracle is supplied to the discovery algorithm.
        for profile in ('normal','congested'):
            for rep in range(args.repetitions):
                order = [1,8]
                random.Random(args.seed+rep).shuffle(order)
                for concurrency in order:
                    await net.reset(profile)
                    table, row = await discover(net, seeds, origin.address, concurrency)
                    row.update(profile=profile, repetition=rep+1, initial_seeds=3)
                    discovery_rows.append(row)
        write_csv(out/'discovery_raw.csv', discovery_rows)
        # The downloader sees only four verified providers from its discovery result.
        peers = [p for p in table.active() if p['id'] in (0,1,2,3)]
        peers.sort(key=lambda p:p['id'])
        if len(peers) != 4:
            raise RuntimeError('discovery did not find all four providers')
        cases = [(p,s,n,r) for p in PROFILES for s in chains for n in (1,2,3,10)
                 for r in range(args.repetitions)]
        random.Random(args.seed).shuffle(cases)
        for case_no, (profile,size,count,rep) in enumerate(cases,1):
            strategies = [False,True]
            random.Random(args.seed+case_no).shuffle(strategies)
            for optimized in strategies:
                await net.reset(profile, chains[size])
                row = await SyncClient(net, peers, optimized, new_node=origin).sync(count)
                row.update(profile=profile, strategy='optimized' if optimized else 'baseline', repetition=rep+1)
                sync_rows.append(row)
                for event in net.m.events:
                    event_rows.append(dict(case=len(sync_rows), profile=profile,
                                           strategy=row['strategy'], **event))
            write_csv(out/'sync_raw.csv', sync_rows)
            if case_no % 10 == 0 or case_no == len(cases):
                print(f'Sync cases {case_no}/{len(cases)}; recorded runs={len(sync_rows)}', flush=True)
        # Real overload sweep: 4 concurrent sync sessions, one provider, capacity two.
        # Short blocks keep the bounded retry budget appropriate to the offered load.
        for profile in ('normal','congested'):
            for rep in range(args.repetitions):
                for workers in (1,2,4,8):
                    await net.reset(profile, chains[262144])
                    t = time.perf_counter()
                    clients = [SyncClient(net,[peers[0]],True,workers) for _ in range(4)]
                    replies = await asyncio.gather(*(c.sync(3) for c in clients), return_exceptions=True)
                    elapsed = time.perf_counter()-t
                    completed = [r for r in replies if isinstance(r,dict) and r['success']]
                    good = len(completed)*3*262144
                    m = net.m
                    load_rows.append({'profile':profile, 'workers_per_client':workers, 'clients':4,
                                      'provider_capacity':2, 'blocks_per_client':3, 'block_bytes':262144,
                                      'repetition':rep+1, 'completed_clients':len(completed),
                                      'elapsed_s':elapsed, 'good_bytes':good, 'received_bytes':m.received,
                                      'throughput_mib_s':good/elapsed/1048576,
                                      'queue_p95_ms':1000*percentile(m.waits,.95),
                                      'queue_peak':m.queue_peak, 'busy':m.busy, 'retries':m.retries,
                                      'timeouts':m.timeouts,
                                      'errors':' | '.join(str(r) for r in replies if isinstance(r,Exception))})
        write_csv(out/'load_raw.csv', load_rows)
        # Lifecycle evidence: join -> verify 100 active peers -> drop five -> two heartbeat rounds.
        await net.reset('normal',chains[65536])
        lifecycle_table, before = await discover(net,seeds,origin.address,8)
        for pid in range(5):
            await net.nodes[pid].stop()
        await maintain(net,lifecycle_table)
        after_one = lifecycle_table.snapshot()
        await maintain(net,lifecycle_table)
        json_write(out/'lifecycle.json', {'nodes_including_newcomer':len(net.nodes),
                   'before':before, 'after_one_round':after_one,
                   'after_two_rounds':lifecycle_table.snapshot(),
                   'active_after_two':len(lifecycle_table.active()),'offline_ids':list(range(5)),
                   'failure_threshold':2,'ttl_s':lifecycle_table.ttl})
    json_write(out/'events.json',event_rows)
    metadata.update(finished_utc=datetime.now(timezone.utc).isoformat(),
                    wall_elapsed_s=time.perf_counter()-started, sync_runs=len(sync_rows),
                    successful_sync_runs=sum(r['success'] for r in sync_rows),
                    discovery_runs=len(discovery_rows), load_runs=len(load_rows),
                    source_unchanged_during_run=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest
                                                   for p,digest in metadata['source_hashes'].items()))
    json_write(out/'metadata.json',metadata)
    print(f'Completed: {len(sync_rows)} sync + {len(discovery_rows)} discovery + {len(load_rows)} load runs.',flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repetitions',type=int,default=3)
    parser.add_argument('--seed',type=int,default=20261027)
    parser.add_argument('--output',default='results')
    parser.add_argument('--fresh',action='store_true',help='Regenerate public fixtures with fresh secret keys')
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error('repetitions must be 1..20')
    if Path(args.output).is_absolute() or '..' in Path(args.output).parts:
        parser.error('output must be a project-relative directory')
    asyncio.run(run(args))
