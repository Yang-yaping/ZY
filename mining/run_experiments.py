"""Run from project root: python -m mining.run_experiments."""
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from .lab import experiment

def main():
    results=[experiment(nodes=n,difficulty=12,rounds=3,repetitions=3) for n in (1,2,4,8)]
    path=Path(__file__).parent/'results'/'benchmark.json'
    path.write_text(json.dumps({'time_utc':datetime.now(timezone.utc).isoformat(),'python':sys.version.split()[0],
      'platform':platform.system()+' '+platform.machine(),'power_measured':False,'runs':results},ensure_ascii=False,indent=2))
    print(path, 'rows=',sum(len(r['rows']) for r in results))
if __name__=='__main__':main()
