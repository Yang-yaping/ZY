"""Single self-contained run used by Streamlit and UI tests."""
from .network import Network, SyncClient, discover, maintain


async def demonstration(chain, count=3, profile='normal', optimized=True, workers=4):
    async with Network(chain) as net:
        origin = await net.add_node(100)
        states = ['新节点高度 0：尚未加入']
        table, discovery = await discover(net, [net.nodes[i].address for i in (0,33,66)],
                                          origin.address, 8 if optimized else 1)
        states.append(f"发现完成：验证 {discovery['active']} 个活跃节点")
        peers = sorted((p for p in table.active() if p['id'] in (0,1,2,3)), key=lambda p:p['id'])
        await net.reset(profile)
        states.append('下载区块：限流、重试、必要时切换提供者')
        row = await SyncClient(net, peers, optimized, workers if optimized else 1, origin).sync(count)
        states.append(f"校验通过：{count*4} 笔 P2PKH 交易，{row['utxo_count']} 个未花费输出")
        states.append(f'同步完成：新节点高度 {origin.available_height}')
        events = list(net.m.events)
        snapshot = table.snapshot()
        for pid in range(5):
            await net.nodes[pid].stop()
        await maintain(net, table)
        await maintain(net, table)
        return {'sync':row, 'discovery':discovery, 'peers':snapshot,
                'after_offline':table.snapshot(), 'active_after_offline':len(table.active()),
                'states':states, 'events':events, 'sample':chain.sample,
                'manifest':chain.manifest[:count], 'profile':profile,
                'strategy':'优化方案' if optimized else '顺序基线', 'listeners':101}
