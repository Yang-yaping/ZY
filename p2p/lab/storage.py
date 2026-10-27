"""Public fixtures contain no private keys; raw files allow independent validation."""
import json
import struct
from pathlib import Path

from .blocks import Chain, Ledger


def save_chain(chain, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'public.json').write_text(json.dumps({
        'manifest':chain.manifest, 'checkpoint':chain.checkpoint, 'sample':chain.sample,
        'genesis':[[tid.hex(), i, v, script.hex()]
                   for (tid, i), (v, script) in chain.genesis_utxos.items()]
    }, indent=2), encoding='utf-8')
    with (folder/'blocks.bin').open('wb') as f:
        for raw in chain.blocks:
            f.write(struct.pack('!I', len(raw)))
            f.write(raw)


def load_chain(folder):
    folder = Path(folder)
    public = json.loads((folder/'public.json').read_text(encoding='utf-8'))
    blocks = []
    with (folder/'blocks.bin').open('rb') as f:
        for entry in public['manifest']:
            length = f.read(4)
            if len(length) != 4 or struct.unpack('!I', length)[0] != entry['bytes']:
                raise ValueError('invalid fixture framing')
            raw = f.read(entry['bytes'])
            if len(raw) != entry['bytes']:
                raise ValueError('truncated fixture')
            blocks.append(raw)
        if f.read(1):
            raise ValueError('trailing fixture bytes')
    genesis = {(bytes.fromhex(t), i):(v, bytes.fromhex(s)) for t, i, v, s in public['genesis']}
    chain = Chain(blocks, public['manifest'], genesis, public['checkpoint'], public['sample'])
    ledger = Ledger(genesis, chain.checkpoint)
    for raw, exp in zip(chain.blocks, chain.manifest):
        ledger.accept(raw, exp)
    return chain
