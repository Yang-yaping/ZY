"""Bitcoin P2PKH transactions inside an explicitly custom teaching block envelope."""
import hashlib
import json
import secrets
import struct
from dataclasses import dataclass

from bitcoin.core import (CMutableTransaction, CMutableTxIn, CMutableTxOut,
                          COutPoint, CTransaction, Hash, Hash160)
from bitcoin.core.key import CECKey
from bitcoin.core.script import (CScript, OP_DUP, OP_HASH160, OP_EQUALVERIFY,
                                OP_CHECKSIG, SignatureHash, SIGHASH_ALL)
from bitcoin.core.scripteval import VerifyScript, SCRIPT_VERIFY_P2SH

MAX_BLOCK = 2 * 1024 * 1024
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':')).encode()


def merkle_root(leaves):
    """Raw internal-order TXID bytes, double SHA-256, duplicate odd last leaf."""
    if not leaves:
        raise ValueError('empty Merkle tree')
    level = list(leaves)
    if any(len(x) != 32 for x in level):
        raise ValueError('invalid Merkle leaf')
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [Hash(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def new_key():
    key = CECKey()
    key.set_secretbytes((secrets.randbelow(ORDER - 1) + 1).to_bytes(32, 'big'))
    key.set_compressed(True)
    return key


def lock_script(pubkey):
    return CScript([OP_DUP, OP_HASH160, Hash160(pubkey), OP_EQUALVERIFY, OP_CHECKSIG])


def signed_spend(key, txid, index, value, script):
    tx = CMutableTransaction([CMutableTxIn(COutPoint(txid, index))],
                             [CMutableTxOut(value - 1, lock_script(key.get_pubkey()))])
    digest = SignatureHash(script, tx, 0, SIGHASH_ALL)
    tx.vin[0].scriptSig = CScript([key.sign(digest) + bytes([SIGHASH_ALL]), key.get_pubkey()])
    VerifyScript(tx.vin[0].scriptSig, script, tx, 0, (SCRIPT_VERIFY_P2SH,))
    return tx


def pack_block(header, transactions, padding):
    head = canonical(header)
    body = struct.pack('!I', len(head)) + head + struct.pack('!I', len(transactions))
    for raw in transactions:
        body += struct.pack('!I', len(raw)) + raw
    return body + struct.pack('!I', len(padding)) + padding


def unpack_block(data):
    if not 1 <= len(data) <= MAX_BLOCK:
        raise ValueError('block size out of bounds')
    pos = 0
    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(data):
            raise ValueError('truncated block')
        out = data[pos:pos+n]
        pos += n
        return out
    def u32():
        return struct.unpack('!I', take(4))[0]
    head_size = u32()
    if head_size > 2048:
        raise ValueError('oversized header')
    header = json.loads(take(head_size))
    if not isinstance(header, dict) or set(header) != {'height', 'previous', 'merkle', 'padding_hash'}:
        raise ValueError('invalid header fields')
    count = u32()
    if not 1 <= count <= 128:
        raise ValueError('transaction count out of bounds')
    raws = [take(u32()) for _ in range(count)]
    padding = take(u32())
    if pos != len(data):
        raise ValueError('trailing block data')
    return header, raws, padding


@dataclass
class Chain:
    blocks: list
    manifest: list
    genesis_utxos: dict
    checkpoint: str
    sample: dict


def make_chain(block_bytes=65536, count=10, seed=20261027):
    if type(block_bytes) is not int or not 4096 <= block_bytes <= MAX_BLOCK:
        raise ValueError('block bytes must be 4096..2097152')
    if type(count) is not int or not 1 <= count <= 10:
        raise ValueError('block count must be 1..10')
    keys = [new_key() for _ in range(4)]
    genesis = {}
    current = []
    for i, key in enumerate(keys):
        tid = Hash(b'teaching-genesis-v1' + bytes([i]))
        script = lock_script(key.get_pubkey())
        genesis[(tid, 0)] = (1000, bytes(script))
        current.append((tid, 0, 1000, script))
    checkpoint = Hash(canonical(sorted((t.hex(), i, v, s.hex())
                                      for (t, i), (v, s) in genesis.items()))).hex()
    blocks, manifest, sample = [], [], {}
    previous = checkpoint
    for height in range(1, count+1):
        txs = []
        for i, key in enumerate(keys):
            tid, idx, value, script = current[i]
            tx = signed_spend(key, tid, idx, value, script)
            txs.append(tx.serialize())
            current[i] = (tx.GetTxid(), 0, value-1, script)
            if not sample:
                sample = {'locking_hex': bytes(script).hex(),
                          'unlocking_hex': bytes(tx.vin[0].scriptSig).hex(),
                          'transaction_hex': tx.serialize().hex(),
                          'locking_asm': 'OP_DUP OP_HASH160 <20-byte pubkey hash> OP_EQUALVERIFY OP_CHECKSIG',
                          'unlocking_asm': '<DER signature + SIGHASH_ALL> <compressed SEC pubkey>'}
        header = {'height': height, 'previous': previous,
                  'merkle': merkle_root([Hash(t) for t in txs]).hex(), 'padding_hash': '0'*64}
        n = block_bytes - len(pack_block(header, txs, b''))
        if n < 0:
            raise ValueError('block too small')
        # Reproducible test payload, not a secret or cryptographic random source.
        padding = hashlib.shake_256(f'{seed}:{block_bytes}:{height}'.encode()).digest(n)
        header['padding_hash'] = Hash(padding).hex()
        raw = pack_block(header, txs, padding)
        previous = Hash(canonical(header)).hex()
        blocks.append(raw)
        manifest.append({'height': height, 'hash': previous, 'previous': header['previous'],
                         'wire_hash': Hash(raw).hex(), 'bytes': len(raw), 'merkle': header['merkle']})
    return Chain(blocks, manifest, genesis, checkpoint, sample)


class Ledger:
    """Validation completes on a private UTXO copy before the block is committed."""
    def __init__(self, genesis, checkpoint):
        self.utxos = dict(genesis)
        self.tip = checkpoint
        self.height = 0

    def accept(self, data, expected):
        if len(data) != expected['bytes'] or Hash(data).hex() != expected['wire_hash']:
            raise ValueError('wire checksum mismatch')
        header, raws, padding = unpack_block(data)
        if type(header['height']) is not int or header['height'] != self.height+1:
            raise ValueError('height mismatch')
        if header['previous'] != self.tip or header['previous'] != expected['previous']:
            raise ValueError('previous hash mismatch')
        tip = Hash(canonical(header)).hex()
        if tip != expected['hash'] or header['merkle'] != merkle_root([Hash(t) for t in raws]).hex():
            raise ValueError('header or Merkle root mismatch')
        if header['padding_hash'] != Hash(padding).hex():
            raise ValueError('payload hash mismatch')
        pending = dict(self.utxos)
        seen = set()
        for raw in raws:
            tx = CTransaction.deserialize(raw)
            if tx.serialize() != raw or tx.GetTxid() in seen or not tx.vin or not tx.vout:
                raise ValueError('duplicate or noncanonical transaction')
            seen.add(tx.GetTxid())
            incoming = 0
            for idx, vin in enumerate(tx.vin):
                point = (vin.prevout.hash, vin.prevout.n)
                if point not in pending:
                    raise ValueError('missing or already spent UTXO')
                value, script = pending[point]
                # Scope: legacy P2PKH, push-only scriptSig, compressed keys, SIGHASH_ALL.
                pushes = list(vin.scriptSig)
                if len(pushes) != 2 or not all(isinstance(v, bytes) for v in pushes):
                    raise ValueError('scriptSig must push signature and public key')
                if len(pushes[1]) != 33 or not pushes[0] or pushes[0][-1] != SIGHASH_ALL:
                    raise ValueError('only compressed P2PKH SIGHASH_ALL is supported')
                VerifyScript(vin.scriptSig, CScript(script), tx, idx, (SCRIPT_VERIFY_P2SH,))
                incoming += value
                del pending[point]
            outgoing = 0
            for idx, out in enumerate(tx.vout):
                if not 0 <= out.nValue <= 21000000 * 100000000:
                    raise ValueError('invalid output amount')
                if len(out.scriptPubKey) != 25 or bytes(out.scriptPubKey)[:3] != b'\x76\xa9\x14' or bytes(out.scriptPubKey)[-2:] != b'\x88\xac':
                    raise ValueError('output must be P2PKH')
                outgoing += out.nValue
                pending[(tx.GetTxid(), idx)] = (out.nValue, bytes(out.scriptPubKey))
            if outgoing > incoming:
                raise ValueError('inflation')
        self.utxos, self.tip, self.height = pending, tip, self.height+1
