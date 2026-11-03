"""Rebuild the public summary after a benchmark run."""
import json
import statistics
from pathlib import Path

def main():
 root=Path(__file__).resolve().parents[1]
 b=json.loads((root/'mining/results/benchmark.json').read_text())
 lines=['# 本机批量实测分析','','固定难度12位，每组3块×3轮；功率全部未测量。','', '|节点|成功/样本|平均哈希次数|平均挖矿秒|标准差秒|平均CPU秒|','|---|---|---|---|---|---|']
 plain=[]
 for run in b['runs']:
  rows=run['rows'];s=run['summary'];sd=statistics.stdev(r['elapsed_s'] for r in rows)
  lines.append(f"|{run['nodes']}|{s['successes']}/{len(rows)}|{s['mean_hashes']:.1f}|{s['mean_elapsed_s']:.6f}|{sd:.6f}|{s['mean_cpu_s']:.6f}|")
  plain.append(f"{run['nodes']}节点：成功{s['successes']}/{len(rows)}，平均哈希{s['mean_hashes']:.1f}次，平均挖矿{s['mean_elapsed_s']:.6f}秒，标准差{sd:.6f}秒，平均CPU{s['mean_cpu_s']:.6f}秒。")
 note='这些样本仅代表本机线程与随机PoW，不能推断节点数带来线性加速。功率未实测，不能据此判断最省电的节点数量。'
 (root/'mining/ANALYSIS.md').write_text('\n'.join(lines)+'\n\n'+note+'\n')
 p=root/'content/coursework.json';qs=json.loads(p.read_text())
 for q in qs:
  if q.get('lab')=='mining':q['answer']=q['answer'].split('\n\n本机实际批量结果')[0]+'\n\n本机实际批量结果（难度12位，各9个样本）：\n'+'\n'.join(plain)+'\n'+note
 p.write_text(json.dumps(qs,ensure_ascii=False,indent=2)+'\n')
 print('\n'.join(lines))
if __name__=='__main__':main()
