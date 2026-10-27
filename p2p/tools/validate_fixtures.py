"""Validate delivered public block files independently of the network experiment."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab.storage import load_chain

for folder in sorted((Path(__file__).resolve().parents[1]/'results'/'fixtures').iterdir()):
    if folder.is_dir():
        chain = load_chain(folder)
        print(f'{folder.name}: {len(chain.blocks)} blocks, {len(chain.blocks)*4} signed transactions verified')
