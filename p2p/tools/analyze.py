"""Audit raw CSVs and generate statistics and publication-style figures."""
import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp'/'mpl'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def analyze(folder):
    meta = json.loads((folder/'metadata.json').read_text())
    sync = pd.read_csv(folder/'sync_raw.csv')
    discovery = pd.read_csv(folder/'discovery_raw.csv')
    load = pd.read_csv(folder/'load_raw.csv')
    expected = 3*4*5*2*meta['repetitions']
    assert meta.get('finished_utc'), 'experiment did not finish'
    assert len(sync)==expected==meta['sync_runs'], 'incomplete matrix'
    assert not sync.duplicated(['profile','block_bytes','blocks','strategy','repetition']).any()
    assert (sync.groupby(['profile','block_bytes','blocks','strategy']).size()==meta['repetitions']).all()
    assert (sync.good_bytes==sync.blocks*sync.block_bytes).all()
    assert (sync.height==sync.blocks).all() and (sync.utxo_count==4).all()
    assert sync.success.all()
    assert np.allclose(sync.throughput_mib_s,sync.good_bytes/sync.elapsed_s/1048576)
    assert np.allclose(sync.transfer_efficiency,sync.good_bytes/sync.received_bytes)
    assert (sync.transfer_efficiency<=1).all()
    assert (sync.validation_s>0).all() and (sync.download_s>0).all()
    assert len(discovery)==4*meta['repetitions'] and (discovery.active==100).all()
    assert len(load)==8*meta['repetitions']
    assert np.allclose(load.throughput_mib_s,load.good_bytes/load.elapsed_s/1048576)
    lifecycle = json.loads((folder/'lifecycle.json').read_text())
    assert lifecycle['active_after_two']==95 and lifecycle['nodes_including_newcomer']==101
    grouped = sync.groupby(['profile','block_bytes','blocks','strategy'],as_index=False).agg(
        mean_s=('elapsed_s','mean'),std_s=('elapsed_s','std'),
        mean_download_s=('download_s','mean'),mean_validation_s=('validation_s','mean'),
        mean_throughput_mib_s=('throughput_mib_s','mean'),mean_efficiency=('transfer_efficiency','mean'),
        mean_queue_p95_ms=('queue_p95_ms','mean'),mean_queue_peak=('queue_peak','mean'),
        mean_retries=('retries','mean'),mean_busy=('busy','mean'),mean_timeouts=('timeouts','mean'))
    grouped.to_csv(folder/'sync_summary.csv',index=False,encoding='utf-8-sig')
    dg = discovery.groupby(['profile','concurrency'],as_index=False).agg(mean_s=('elapsed_s','mean'),std_s=('elapsed_s','std'),
                                                                         mean_probes=('probes','mean'),active=('active','min'))
    dg.to_csv(folder/'discovery_summary.csv',index=False,encoding='utf-8-sig')
    lg = load.groupby(['profile','workers_per_client'],as_index=False).agg(mean_s=('elapsed_s','mean'),std_s=('elapsed_s','std'),
                    throughput=('throughput_mib_s','mean'),busy=('busy','mean'),retries=('retries','mean'),
                    queue_p95_ms=('queue_p95_ms','mean'),completed=('completed_clients','mean'))
    lg.to_csv(folder/'load_summary.csv',index=False,encoding='utf-8-sig')
    figures = folder/'figures'
    figures.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'figure.facecolor':'white','axes.grid':True,'grid.alpha':.2})
    profiles = ['normal','disconnect','unresponsive','overloaded','congested']
    colors = {'baseline':'#c77542','optimized':'#245c96'}
    fig, axes = plt.subplots(2,3,figsize=(11,6.1),layout='constrained')
    for ax, profile in zip(axes.flat,profiles):
        for strategy in ('baseline','optimized'):
            g = grouped[(grouped.profile==profile)&(grouped.block_bytes==1048576)&(grouped.strategy==strategy)].sort_values('blocks')
            ax.errorbar(g.blocks,g.mean_s,yerr=g.std_s,marker='o',capsize=3,label=strategy,color=colors[strategy])
        ax.set(title=profile,xlabel='Blocks to sync',ylabel='Total time (s)',xticks=[1,2,3,10])
    axes.flat[5].axis('off')
    axes.flat[5].text(.02,.9,'100 existing nodes + 1 newcomer\n1 MiB per block, 4 P2PKH tx/block\nSame 4 providers for both strategies\n3 repetitions; error bars = sample SD\nReal loopback TCP + impairment model',va='top',linespacing=1.8)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    axes.flat[5].legend(handles,labels,loc='lower left',frameon=False)
    fig.savefig(figures/'sync_times.png',dpi=190)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.5,3.8),layout='constrained')
    x = np.arange(2)
    for j, concurrency in enumerate((1,8)):
        g = dg[dg.concurrency==concurrency].set_index('profile').loc[['normal','congested']]
        ax.bar(x+(j-.5)*.32,g.mean_s,width=.32,yerr=g.std_s,capsize=3,label=f'{concurrency} concurrent probes',color=['#c77542','#245c96'][j])
    ax.set(xticks=x,xticklabels=['2 ms response delay','15 ms response delay'],ylabel='Discover 100 live peers (s)')
    ax.legend(frameon=False)
    fig.savefig(figures/'discovery.png',dpi=190)
    plt.close(fig)
    fig, axes = plt.subplots(1,2,figsize=(9,3.7),layout='constrained')
    for profile, color in [('normal','#245c96'),('congested','#c77542')]:
        g = lg[lg.profile==profile].sort_values('workers_per_client')
        axes[0].plot(g.workers_per_client,g.throughput,'o-',label=profile,color=color)
        axes[1].plot(g.workers_per_client,g.busy,'o-',label=profile,color=color)
    axes[0].set(xlabel='Workers per client (4 clients)',ylabel='Verified group goodput (MiB/s)',xticks=[1,2,4,8])
    axes[1].set(xlabel='Workers per client (4 clients)',ylabel='Mean BUSY responses',xticks=[1,2,4,8])
    axes[0].legend(frameon=False)
    fig.savefig(figures/'load.png',dpi=190)
    plt.close(fig)
    comparison = grouped[grouped.blocks==10].pivot(index=['profile','block_bytes'],columns='strategy',values='mean_s').reset_index()
    comparison['speedup'] = comparison.baseline/comparison.optimized
    comparison.to_csv(folder/'ten_block_comparison.csv',index=False,encoding='utf-8-sig')
    audit = {'passed':True,'matrix_runs':len(sync),'matrix_successful':int(sync.success.sum()),
             'matrix_groups':len(grouped),'discovery_runs':len(discovery),'load_runs':len(load),
             'completed_load_clients':int(load.completed_clients.sum()),'offered_load_clients':len(load)*4,
             'source_unchanged_during_run':meta.get('source_unchanged_during_run'),
             'all_checks':'matrix completeness, no duplicate keys, success, heights, UTXOs, recomputed rates, active peers, lifecycle'}
    (folder/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    print(json.dumps(audit,ensure_ascii=False,indent=2))
    print(comparison.to_string(index=False))
    print(dg.to_string(index=False))
    print(lg.to_string(index=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',default='results')
    args = p.parse_args()
    analyze(ROOT/args.input)
