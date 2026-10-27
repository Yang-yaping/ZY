"""Functional, cryptographic and real loopback TCP checks; unittest only."""
import asyncio
import copy
import time
import unittest
import tempfile
from pathlib import Path

from bitcoin.core import CMutableTransaction, Hash
from bitcoin.core.script import CScript, SignatureHash, SIGHASH_ALL

from lab.blocks import (make_chain, Ledger, merkle_root, unpack_block, pack_block,
                        canonical, new_key, lock_script, signed_spend)
from lab.network import Network, SyncClient, discover, maintain, PeerTable, valid_address
from lab.storage import save_chain, load_chain


def rewrap(header, raws, padding, expected):
    """Let a malformed block reach semantic validation instead of transport hash rejection."""
    h = dict(header)
    h['merkle'] = merkle_root([Hash(x) for x in raws]).hex()
    raw = pack_block(h, raws, padding)
    exp = dict(expected, bytes=len(raw), wire_hash=Hash(raw).hex(), hash=Hash(canonical(h)).hex())
    return raw, exp


class CryptoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chain = make_chain(4096, 3)

    def test_three_blocks_real_scripts_and_utxo(self):
        c = self.chain
        ledger = Ledger(c.genesis_utxos, c.checkpoint)
        for raw, expected in zip(c.blocks, c.manifest):
            ledger.accept(raw, expected)
        self.assertEqual(ledger.height, 3)
        self.assertEqual(len(ledger.utxos), 4)
        self.assertEqual(sum(v for v, _ in ledger.utxos.values()), 3988)

    def test_bitcoin_merkle_odd_leaf(self):
        a, b, c = [Hash(bytes([i])) for i in range(3)]
        self.assertEqual(merkle_root([a, b, c]), Hash(Hash(a+b)+Hash(c+c)))
        self.assertEqual(merkle_root([a]), a)
        with self.assertRaises(ValueError):
            merkle_root([])

    def reject_without_commit(self, raw, expected):
        c = self.chain
        ledger = Ledger(c.genesis_utxos, c.checkpoint)
        before = copy.deepcopy(ledger.utxos)
        with self.assertRaises(Exception):
            ledger.accept(raw, expected)
        self.assertEqual(ledger.height, 0)
        self.assertEqual(ledger.tip, c.checkpoint)
        self.assertEqual(ledger.utxos, before)

    def test_tampered_body(self):
        c = self.chain
        raw = c.blocks[0][:-1]+bytes([c.blocks[0][-1] ^ 1])
        self.reject_without_commit(raw, c.manifest[0])

    def test_bad_signature_even_when_all_hashes_recomputed(self):
        c = self.chain
        h, raws, pad = unpack_block(c.blocks[0])
        tx = CMutableTransaction.from_tx(CMutableTransaction.deserialize(raws[1]))
        sig, pub = list(tx.vin[0].scriptSig)
        other = new_key()
        tx.vin[0].scriptSig = CScript([other.sign(Hash(b'wrong message'))+b'\x01', pub])
        raws[1] = tx.serialize()
        self.reject_without_commit(*rewrap(h, raws, pad, c.manifest[0]))

    def test_inflation_signed_with_correct_key(self):
        key = new_key()
        script = lock_script(key.get_pubkey())
        tid = Hash(b'isolated inflation fixture')
        tx = signed_spend(key, tid, 0, 1000, script)
        tx.vout[0].nValue = 1001
        tx.vin[0].scriptSig = CScript([key.sign(SignatureHash(script, tx, 0, SIGHASH_ALL))+b'\x01', key.get_pubkey()])
        h, _, pad = unpack_block(self.chain.blocks[0])
        raw, exp = rewrap(h, [tx.serialize()], pad, self.chain.manifest[0])
        ledger = Ledger({(tid, 0):(1000, bytes(script))}, self.chain.checkpoint)
        with self.assertRaisesRegex(ValueError, 'inflation'):
            ledger.accept(raw, exp)
        self.assertEqual(ledger.height, 0)

    def test_duplicate_spend_and_previous_hash(self):
        c = self.chain
        h, raws, pad = unpack_block(c.blocks[0])
        self.reject_without_commit(*rewrap(h, [raws[0], raws[0]], pad, c.manifest[0]))
        h['previous'] = 'f'*64
        self.reject_without_commit(*rewrap(h, raws, pad, c.manifest[0]))

    def test_merkle_and_payload_separately(self):
        c = self.chain
        h, raws, pad = unpack_block(c.blocks[0])
        h['merkle'] = '0'*64
        raw = pack_block(h, raws, pad)
        exp = dict(c.manifest[0], wire_hash=Hash(raw).hex(), hash=Hash(canonical(h)).hex())
        self.reject_without_commit(raw, exp)
        h, raws, pad = unpack_block(c.blocks[0])
        h['padding_hash'] = '0'*64
        self.reject_without_commit(*rewrap(h, raws, pad, c.manifest[0]))

    def test_input_bounds(self):
        for size in [True, -1, 0, 3, 3*1024*1024]:
            with self.assertRaises(ValueError):
                make_chain(size, 1)
        self.assertFalse(valid_address(None))
        self.assertFalse(valid_address({'id':1,'host':'example.com','port':80}))
        self.assertFalse(valid_address({'id':True,'host':'127.0.0.1','port':80}))

    def test_ttl_and_failure_threshold(self):
        table = PeerTable(ttl=.01)
        a = {'id':1,'host':'127.0.0.1','port':12345}
        table.seen(a)
        table.failed(1)
        self.assertEqual(len(table.active()), 1)
        table.failed(1)
        self.assertEqual(len(table.active()), 0)
        table.seen(a)
        table.peers[1].last_seen = time.monotonic()-.02
        self.assertEqual(len(table.active()), 0)

    def test_public_fixture_roundtrip_and_truncation(self):
        folder = Path(__file__).resolve().parents[1]/'tmp'
        folder.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as tmp:
            save_chain(self.chain,tmp)
            loaded = load_chain(tmp)
            self.assertEqual(loaded.blocks,self.chain.blocks)
            path = Path(tmp)/'blocks.bin'
            path.write_bytes(path.read_bytes()[:-1])
            with self.assertRaises(ValueError):
                load_chain(tmp)


class NetworkTests(unittest.IsolatedAsyncioTestCase):
    async def test_101_nodes_join_discovery_and_maintenance(self):
        async with Network(make_chain(4096, 1)) as net:
            origin = await net.add_node(100)
            table, result = await discover(net, [net.nodes[0].address], origin.address, 8)
            self.assertEqual(len(net.nodes), 101)
            self.assertEqual(result['active'], 100)
            self.assertIn(100, net.nodes[0].peers)
            for pid in range(5):
                await net.nodes[pid].stop()
            await maintain(net, table)
            await maintain(net, table)
            self.assertEqual(len(table.active()), 95)

    async def test_counts_one_two_three_ten(self):
        async with Network(make_chain(4096, 10)) as net:
            newcomer = await net.add_node(100)
            peers = [net.nodes[i].address for i in range(4)]
            for count in (1, 2, 3, 10):
                await net.reset()
                self.assertEqual((await net.rpc(newcomer.address, {'cmd':'HEADERS'}))['manifest'], [])
                self.assertEqual((await net.rpc(newcomer.address, {'cmd':'GET','height':1}))['status'], 'INVALID')
                row = await SyncClient(net, peers, new_node=newcomer).sync(count)
                self.assertEqual(row['height'], count)
                self.assertEqual(row['utxo_count'], 4)
                self.assertTrue(row['success'])
                self.assertEqual(newcomer.available_height, count)

    async def test_failures_recover_and_corrupt_data_is_rejected(self):
        async with Network(make_chain(65536, 3)) as net:
            peers = [net.nodes[i].address for i in range(4)]
            for profile, metric in [('disconnect','disconnects'), ('unresponsive','timeouts'),
                                    ('overloaded','busy'), ('corrupt','checksum_failures')]:
                await net.reset(profile)
                row = await SyncClient(net, peers).sync(3)
                self.assertTrue(row['success'])
                self.assertGreater(row[metric], 0, profile)

    async def test_resume_saves_retransmitted_bytes(self):
        async with Network(make_chain(65536, 1)) as net:
            peers = [net.nodes[i].address for i in range(4)]
            rows = []
            for optimized in (False, True):
                await net.reset('disconnect')
                rows.append(await SyncClient(net, peers, optimized).sync(1))
            self.assertGreater(rows[0]['received_bytes'], rows[1]['received_bytes'])
            self.assertEqual(rows[1]['received_bytes'], 65536)

    async def test_server_rejects_invalid_request(self):
        async with Network(make_chain(4096, 1), count=1) as net:
            a = net.nodes[0].address
            for request in [{'cmd':'GET','height':True}, {'cmd':'GET','height':1,'offset':-1},
                            {'cmd':'DELETE'}]:
                self.assertEqual((await net.rpc(a, request))['status'], 'INVALID')
            with self.assertRaises(ValueError):
                await discover(net, [a], a, 0)

    async def test_exhausted_retry_cancels_sibling_downloads(self):
        async with Network(make_chain(4096, 10)) as net:
            await net.reset('unresponsive')
            with self.assertRaisesRegex(RuntimeError, 'retry budget'):
                await SyncClient(net,[net.nodes[0].address],True,4).sync(10)
            names = [getattr(t.get_coro(),'__qualname__','') for t in asyncio.all_tasks()
                     if t is not asyncio.current_task() and not t.done()]
            self.assertFalse(any('SyncClient' in n for n in names),names)


if __name__ == '__main__':
    unittest.main(verbosity=2)
