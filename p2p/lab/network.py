"""Real loopback TCP with reproducible application-layer impairment injection."""
import asyncio
import json
import math
import random
import struct
import time
from dataclasses import dataclass, field

from .blocks import MAX_BLOCK, Ledger

PROFILES = {
    'normal': dict(latency=.002, rate=16*1024*1024),
    'disconnect': dict(latency=.002, rate=16*1024*1024),
    'unresponsive': dict(latency=.002, rate=16*1024*1024),
    'overloaded': dict(latency=.002, rate=16*1024*1024),
    'congested': dict(latency=.015, rate=2*1024*1024),
}
LABELS = {'normal':'正常', 'disconnect':'连接中断', 'unresponsive':'节点不响应',
          'overloaded':'并发请求过多', 'congested':'带宽受限与高延迟'}


def percentile(values, p):
    if not values:
        return 0.
    a = sorted(values)
    return a[min(len(a)-1, math.ceil(p*len(a))-1)]


async def send_json(writer, value):
    data = json.dumps(value, separators=(',', ':')).encode()
    if len(data) > 65536:
        raise ValueError('control message too large')
    writer.write(struct.pack('!I', len(data)) + data)
    await writer.drain()


async def read_json(reader, timeout=.25):
    length = struct.unpack('!I', await asyncio.wait_for(reader.readexactly(4), timeout))[0]
    if not 1 <= length <= 65536:
        raise ValueError('invalid frame length')
    obj = json.loads(await asyncio.wait_for(reader.readexactly(length), timeout))
    if not isinstance(obj, dict):
        raise ValueError('control frame must be an object')
    return obj


@dataclass
class Metrics:
    sent: int = 0
    received: int = 0
    requests: int = 0
    connections: int = 0
    busy: int = 0
    disconnects: int = 0
    timeouts: int = 0
    checksum_failures: int = 0
    retries: int = 0
    queue_peak: int = 0
    service_s: float = 0.
    waits: list = field(default_factory=list)
    events: list = field(default_factory=list)

    def event(self, kind, **kwargs):
        self.events.append({'kind': kind, **kwargs})


class Bottleneck:
    """One FIFO serialization resource shared by all simulated data connections.

    This is an application bandwidth/queue model, not a replacement TCP algorithm.
    Metadata and HELLO control packets bypass it and are excluded from data goodput.
    """
    def __init__(self, rate, metrics):
        self.rate, self.m = rate, metrics
        self.lock = asyncio.Lock()
        self.waiting = 0

    async def send(self, writer, data):
        start = time.perf_counter()
        self.waiting += 1
        self.m.queue_peak = max(self.m.queue_peak, self.waiting-1)
        try:
            async with self.lock:
                self.m.waits.append(time.perf_counter()-start)
                t = time.perf_counter()
                await asyncio.sleep(len(data)/self.rate)
                writer.write(data)
                await writer.drain()
                self.m.sent += len(data)
                self.m.service_s += time.perf_counter()-t
        finally:
            self.waiting -= 1


@dataclass
class Peer:
    address: dict
    last_seen: float
    rtt_ms: float
    failures: int = 0


class PeerTable:
    def __init__(self, ttl=30., failure_limit=2):
        self.ttl, self.failure_limit = ttl, failure_limit
        self.peers = {}

    def seen(self, address, rtt_ms=0.):
        self.peers[address['id']] = Peer(dict(address), time.monotonic(), rtt_ms)

    def failed(self, pid):
        if pid in self.peers:
            self.peers[pid].failures += 1

    def active(self):
        now = time.monotonic()
        return [p.address for p in self.peers.values()
                if now-p.last_seen <= self.ttl and p.failures < self.failure_limit]

    def snapshot(self):
        active_ids = {p['id'] for p in self.active()}
        return [{'id': pid, 'port': p.address['port'], 'failures': p.failures,
                 'rtt_ms': p.rtt_ms, 'active': pid in active_ids}
                for pid, p in sorted(self.peers.items())]


class Node:
    def __init__(self, network, pid):
        self.net, self.pid = network, pid
        self.peers = {}
        self.server = None
        self.active = 0
        self.capacity = 2
        self.cut = set()
        self.available_height = 0

    async def start(self):
        self.server = await asyncio.start_server(self.handle, '127.0.0.1', 0)
        self.address = {'id': self.pid, 'host': '127.0.0.1',
                        'port': self.server.sockets[0].getsockname()[1]}

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.net.handlers.add(task)
        counted = False
        try:
            request = await read_json(reader)
            cmd = request.get('cmd')
            if cmd in ('HELLO', 'PING', 'HEADERS'):
                await asyncio.sleep(self.net.latency)
                if cmd == 'HELLO':
                    origin = request.get('origin')
                    if isinstance(origin, dict) and valid_address(origin):
                        self.peers[origin['id']] = origin
                    await send_json(writer, {'status':'OK', 'node':self.address,
                                           'peers':list(self.peers.values())[:128]})
                elif cmd == 'HEADERS':
                    await send_json(writer, {'status':'OK', 'manifest':self.net.chain.manifest[:self.available_height]})
                else:
                    await send_json(writer, {'status':'OK', 'node':self.address})
                return
            if cmd != 'GET':
                await send_json(writer, {'status':'INVALID'})
                return
            self.net.m.requests += 1
            height, offset = request.get('height'), request.get('offset', 0)
            if type(height) is not int or not 1 <= height <= self.available_height:
                await send_json(writer, {'status':'INVALID'})
                return
            raw = self.net.chain.blocks[height-1]
            if type(offset) is not int or not 0 <= offset <= len(raw):
                await send_json(writer, {'status':'INVALID'})
                return
            if self.active >= self.capacity or (self.net.profile == 'overloaded' and
                                                time.perf_counter() < self.net.busy_until):
                self.net.m.busy += 1
                await send_json(writer, {'status':'BUSY', 'retry_after':.01})
                return
            self.active += 1
            counted = True
            if self.net.profile == 'unresponsive' and self.pid == 0:
                # Server accepts TCP but intentionally gives no application response.
                await asyncio.sleep(2)
                return
            await asyncio.sleep(self.net.latency)
            await send_json(writer, {'status':'OK', 'length':len(raw)-offset, 'total':len(raw)})
            body = raw[offset:]
            if self.net.profile == 'corrupt' and self.pid == 0:
                body = body[:-1] + bytes([body[-1] ^ 1])
            cut = self.net.profile == 'disconnect' and self.pid == 0 and height not in self.cut
            if cut:
                self.cut.add(height)
                body = body[:max(1, len(body)//2)]
            for at in range(0, len(body), 16384):
                await self.net.link.send(writer, body[at:at+16384])
            if cut:
                self.net.m.disconnects += 1
                self.net.m.event('disconnect', peer=self.pid, height=height, offset=offset)
                writer.transport.abort()
        except (ConnectionError, OSError, ValueError, asyncio.IncompleteReadError, asyncio.TimeoutError):
            pass
        finally:
            if counted:
                self.active -= 1
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            self.net.handlers.discard(task)


def valid_address(a):
    return (isinstance(a, dict) and set(a) == {'id', 'host', 'port'} and type(a['id']) is int and
            0 <= a['id'] <= 10000 and a['host'] == '127.0.0.1' and
            type(a['port']) is int and 1 <= a['port'] <= 65535)


class Network:
    def __init__(self, chain, count=100, seed=20261027):
        if type(count) is not int or not 1 <= count <= 200:
            raise ValueError('node count must be 1..200')
        self.chain, self.count, self.seed = chain, count, seed
        self.nodes = {}
        self.handlers = set()
        self.reset_values('normal')

    def reset_values(self, profile):
        if profile not in PROFILES and profile != 'corrupt':
            raise ValueError('unknown network profile')
        self.profile = profile
        config = PROFILES.get(profile, PROFILES['normal'])
        self.latency = config['latency']
        self.m = Metrics()
        self.link = Bottleneck(config['rate'], self.m)
        self.busy_until = time.perf_counter()+.04 if profile == 'overloaded' else 0
        for node in self.nodes.values():
            node.cut.clear()
            node.active = 0
            node.available_height = len(self.chain.blocks) if node.pid < self.count else 0

    async def reset(self, profile='normal', chain=None):
        await self.quiesce()
        if chain:
            self.chain = chain
        self.reset_values(profile)

    async def quiesce(self):
        tasks = list(self.handlers)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def __aenter__(self):
        for pid in range(self.count):
            await self.add_node(pid, ready=True)
        rng = random.Random(self.seed)  # Topology only; never a signing key source.
        for pid, node in self.nodes.items():
            ids = {(pid-1) % self.count, (pid+1) % self.count}
            ids.update(rng.sample(range(self.count), min(8, self.count)))
            node.peers = {i:self.nodes[i].address for i in ids if i != pid}
        return self

    async def add_node(self, pid, ready=False):
        if pid in self.nodes:
            raise ValueError('node id already exists')
        node = Node(self, pid)
        node.available_height = len(self.chain.blocks) if ready else 0
        await node.start()
        self.nodes[pid] = node
        return node

    async def __aexit__(self, *args):
        await asyncio.gather(*(n.stop() for n in self.nodes.values()))
        await self.quiesce()

    async def rpc(self, address, request, timeout=.15):
        if not valid_address(address):
            raise ValueError('invalid peer address')
        reader = writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(address['host'], address['port']), timeout)
            self.m.connections += 1
            await send_json(writer, request)
            return await read_json(reader, timeout)
        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except (ConnectionError, OSError):
                    pass


async def discover(net, seeds, origin, concurrency=1, target=100):
    """BFS gossip. Same target for both strategies; only known seeds are supplied."""
    if type(concurrency) is not int or not 1 <= concurrency <= 32:
        raise ValueError('discovery concurrency must be 1..32')
    if type(target) is not int or not 1 <= target <= 200:
        raise ValueError('discovery target must be 1..200')
    if not valid_address(origin) or any(not valid_address(a) for a in seeds):
        raise ValueError('invalid discovery address')
    table, pending, visited = PeerTable(), {a['id']:a for a in seeds}, set()
    async def probe(address):
        start = time.perf_counter()
        try:
            reply = await net.rpc(address, {'cmd':'HELLO', 'origin':origin})
            if reply.get('status') != 'OK' or reply.get('node') != address:
                raise ValueError('invalid HELLO')
            return address, reply, (time.perf_counter()-start)*1000
        except (OSError, ValueError, asyncio.TimeoutError, asyncio.IncompleteReadError):
            return address, None, 0
    start = time.perf_counter()
    probes = 0
    while pending and len(table.active()) < target:
        batch = list(pending.values())[:min(concurrency, target-len(table.active()))]
        for a in batch:
            pending.pop(a['id'], None)
            visited.add(a['id'])
        for address, reply, rtt in await asyncio.gather(*(probe(a) for a in batch)):
            probes += 1
            if not reply:
                continue
            table.seen(address, rtt)
            for candidate in reply['peers']:
                if valid_address(candidate) and candidate['id'] != origin['id'] and candidate['id'] not in visited:
                    pending[candidate['id']] = candidate
    return table, {'elapsed_s':time.perf_counter()-start, 'probes':probes,
                   'active':len(table.active()), 'concurrency':concurrency}


async def maintain(net, table, concurrency=8):
    if type(concurrency) is not int or not 1 <= concurrency <= 32:
        raise ValueError('maintenance concurrency must be 1..32')
    sem = asyncio.Semaphore(concurrency)
    async def ping(pid, peer):
        async with sem:
            try:
                r = await net.rpc(peer.address, {'cmd':'PING'}, timeout=.05)
                if r['status'] != 'OK':
                    raise ValueError('bad ping')
                table.seen(peer.address)
            except (OSError, ValueError, asyncio.TimeoutError, asyncio.IncompleteReadError):
                table.failed(pid)
    await asyncio.gather(*(ping(pid, p) for pid, p in list(table.peers.items())))


class SyncClient:
    def __init__(self, net, peers, optimized=True, workers=None, new_node=None):
        if not peers:
            raise ValueError('no peer available')
        self.net, self.peers, self.optimized = net, list(peers), optimized
        self.new_node = new_node
        self.workers = workers if workers is not None else (4 if optimized else 1)
        if type(self.workers) is not int or not 1 <= self.workers <= 32:
            raise ValueError('workers must be 1..32')
        self.failed_until, self.cursor = {}, 0

    def select(self, height, attempt):
        if not self.optimized:
            return self.peers[attempt % len(self.peers)]
        now = time.perf_counter()
        eligible = [p for p in self.peers if self.failed_until.get(p['id'], 0) <= now]
        pool = eligible or self.peers
        peer = pool[self.cursor % len(pool)]
        self.cursor += 1
        return peer

    async def fetch(self, expected):
        saved = bytearray()
        from bitcoin.core import Hash
        for attempt in range(30):
            peer = self.select(expected['height'], attempt)
            writer = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(peer['host'], peer['port']), .15)
                self.net.m.connections += 1
                offset = len(saved) if self.optimized else 0
                if not self.optimized:
                    saved.clear()
                await send_json(writer, {'cmd':'GET', 'height':expected['height'], 'offset':offset})
                reply = await read_json(reader, .12)
                if reply.get('status') == 'BUSY':
                    raise ConnectionError('BUSY')
                if reply.get('status') != 'OK' or reply.get('total') != expected['bytes'] or reply.get('length') != expected['bytes']-offset:
                    raise ValueError('invalid GET response')
                while len(saved) < expected['bytes']:
                    chunk = await asyncio.wait_for(reader.read(min(16384, expected['bytes']-len(saved))), .5)
                    if not chunk:
                        raise ConnectionError('stream interrupted')
                    saved.extend(chunk)
                    self.net.m.received += len(chunk)
                if Hash(saved).hex() != expected['wire_hash']:
                    self.net.m.checksum_failures += 1
                    saved.clear()
                    raise ValueError('checksum mismatch')
                return bytes(saved)
            except (ConnectionError, OSError, ValueError, asyncio.TimeoutError, asyncio.IncompleteReadError) as error:
                if isinstance(error, asyncio.TimeoutError):
                    self.net.m.timeouts += 1
                if self.optimized:
                    self.failed_until[peer['id']] = time.perf_counter()+.08
                self.net.m.retries += 1
                self.net.m.event('retry', peer=peer['id'], height=expected['height'],
                                 offset=len(saved), reason=type(error).__name__+':'+str(error))
                await asyncio.sleep(min(.005*(attempt+1), .03))
            finally:
                if writer:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except (ConnectionError, OSError):
                        pass
        raise RuntimeError('retry budget exhausted')

    async def sync(self, count):
        if type(count) is not int or not 1 <= count <= 10:
            raise ValueError('sync count must be 1..10')
        started = time.perf_counter()
        # Header agreement is anchored by a preconfigured checkpoint, not consensus.
        reply = await self.net.rpc(self.peers[0], {'cmd':'HEADERS'})
        manifest = reply['manifest'][:count]
        if len(manifest) != count or manifest[-1]['hash'] != self.net.chain.manifest[count-1]['hash']:
            raise ValueError('untrusted tip')
        previous = self.net.chain.checkpoint
        for i, h in enumerate(manifest, 1):
            if h['height'] != i or h['previous'] != previous or not 1 <= h['bytes'] <= MAX_BLOCK:
                raise ValueError('unlinked headers')
            previous = h['hash']
        sem = asyncio.Semaphore(self.workers)
        async def get(h):
            async with sem:
                return await self.fetch(h)
        tasks = [asyncio.create_task(get(h)) for h in manifest]
        try:
            raw = await asyncio.gather(*tasks)
        except BaseException:
            # gather does not cancel siblings when one child raises. Drain them
            # before another case can reset shared counters or replace a chain.
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        download_done = time.perf_counter()
        ledger = Ledger(self.net.chain.genesis_utxos, self.net.chain.checkpoint)
        for data, h in zip(raw, manifest):
            ledger.accept(data, h)
        if self.new_node is not None:
            self.new_node.available_height = ledger.height
        done = time.perf_counter()
        good = sum(len(x) for x in raw)
        m = self.net.m
        return {'blocks':count, 'block_bytes':manifest[0]['bytes'], 'workers':self.workers,
                'download_s':download_done-started, 'validation_s':done-download_done,
                'elapsed_s':done-started, 'good_bytes':good, 'received_bytes':m.received,
                'sent_bytes':m.sent, 'throughput_mib_s':good/(done-started)/1048576,
                'transfer_efficiency':good/m.received if m.received else 0,
                'queue_p95_ms':1000*percentile(m.waits,.95), 'queue_peak':m.queue_peak,
                'link_busy_fraction':m.service_s/(done-started), 'busy':m.busy,
                'timeouts':m.timeouts, 'disconnects':m.disconnects, 'retries':m.retries,
                'checksum_failures':m.checksum_failures, 'height':ledger.height,
                'utxo_count':len(ledger.utxos), 'tip':ledger.tip, 'success':True}
