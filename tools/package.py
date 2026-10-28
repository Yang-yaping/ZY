"""Create a portable source/data archive without live wallets or environments."""
import hashlib
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SKIP={'.venv','tmp','__pycache__','.git','deliverables','data'}


def include(path):
    return (not any(p in SKIP for p in path.relative_to(ROOT).parts)
            and path.suffix not in {'.pyc','.docx','.pdf','.zip'}
            and not path.name.endswith(('.db','.db-wal','.db-shm'))
            and path.name not in {'.DS_Store','secrets.toml','MANIFEST.sha256'})


files=sorted(p for p in ROOT.rglob('*') if p.is_file() and include(p))
manifest=ROOT/'MANIFEST.sha256'
manifest.write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}\n'
                           for p in files),encoding='utf-8')
files.append(manifest)
output=ROOT/'deliverables'
output.mkdir(exist_ok=True)
target=output/'隐币实验室_可操作新版_待确认.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in files:
        z.write(p,(Path(ROOT.name)/p.relative_to(ROOT)).as_posix())
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None,'ZIP CRC failure'
print(f'{target}\n{len(files)} files, {target.stat().st_size/1048576:.2f} MiB, CRC OK')
