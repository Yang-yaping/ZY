"""Package only deliverable sources, public fixtures and measured results."""
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
excluded = {'.venv','.git','__pycache__','tmp','deliverables','.DS_Store'}


def included(path):
    parts = path.relative_to(ROOT).parts
    return not any(p in excluded for p in parts) and path.suffix not in ('.pyc','.docx','.pdf') and path.name!='secrets.toml'


files = sorted(p for p in ROOT.rglob('*') if p.is_file() and included(p) and p.name!='MANIFEST.sha256')
manifest = ROOT/'MANIFEST.sha256'
manifest.write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}\n'
                            for p in files),encoding='utf-8')
files.append(manifest)
out = ROOT/'deliverables'
out.mkdir(exist_ok=True)
target = out/'P2P网络与区块同步实验_待确认.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for path in files:
        z.write(path,(Path(ROOT.name)/path.relative_to(ROOT)).as_posix())
with zipfile.ZipFile(target) as z:
    if z.testzip() is not None:
        raise RuntimeError('archive CRC failure')
print(f'{target}\n{len(files)} files; {target.stat().st_size/1048576:.2f} MiB; CRC OK')
