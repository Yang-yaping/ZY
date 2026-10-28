/* Trusted UI code. All user/backend text is escaped or assigned as textContent.
   Forms send commands through Streamlit's session-bound bidirectional channel. */
function mountLab(root, initial, send) {
  const $ = selector => root.querySelector(selector);
  const $$ = selector => [...root.querySelectorAll(selector)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const short = value => String(value || '').slice(0, 12);
  const json = value => esc(JSON.stringify(value, null, 2));
  const labels = ['首页', '线上银行', '节点模拟器', '课程作业'];
  const sceneIds = ['home', 'bank', 'nodes', 'coursework'];
  const profiles = {normal:'正常', disconnect:'连接中断', unresponsive:'节点不响应', overloaded:'并发请求过多', congested:'带宽受限与高延迟'};
  const ui = {bankTab:'银行', nodeTab:'实验控制台', fields:{}, details:{}, qid:null, answers:{}, current:initial.initial || 0};
  const media = matchMedia('(prefers-reduced-motion: reduce)');
  const gate = new YinbiMotion.WheelIntent();
  let data = initial, sender = send, request = null, moving = false, pending = null, targetNav = ui.current, touch = null;
  const scenes = $$('.scene');
  const animations = new Set();
  let imageReady = false;
  function remember(container) {
    container.querySelectorAll('details').forEach(el=>{ui.details[el.querySelector('summary').textContent]=el.open;});
    container.querySelectorAll('input[id],select[id],textarea[id]').forEach(el => {
      if (el.type !== 'file') ui.fields[el.id] = el.type === 'checkbox' ? el.checked : el.value;
    });
  }
  function restore(container) {
    container.querySelectorAll('details').forEach(el=>{const k=el.querySelector('summary').textContent;if(k in ui.details)el.open=ui.details[k];});
    container.querySelectorAll('input[id],select[id],textarea[id]').forEach(el => {
      if (!(el.id in ui.fields)) return;
      if (el.type === 'checkbox') el.checked = ui.fields[el.id];
      else if (el.tagName !== 'SELECT' || [...el.options].some(o => o.value === ui.fields[el.id])) el.value = ui.fields[el.id];
    });
    if (request) container.querySelectorAll('[data-command],button[type=submit]').forEach(b => b.disabled = true);
  }
  const option = (value, label=value) => `<option value="${esc(value)}">${esc(label)}</option>`;
  const field = (id, label, name, value='', type='text') => `<label>${esc(label)}<input id="${id}" name="${name}" type="${type}" value="${esc(value)}" ${type === 'password' ? 'maxlength="128" autocomplete="off"' : 'maxlength="100"'} required></label>`;
  const select = (id, label, name, options) => `<label>${esc(label)}<select id="${id}" name="${name}">${options}</select></label>`;
  const empty = text => `<div class="empty">${esc(text)}</div>`;
  const button = (label, command, extra='', primary=false) => `<button type="submit" class="${primary?'primary':'button'}" data-command="${command}" ${extra}>${label}</button>`;
  const tag = value => `<span class="tag ${['DUPLICATE','CANCELLED','REJECTED'].includes(value)?'bad':''}">${esc(value)}</span>`;
  function table(rows, columns) {
    if (!rows?.length) return empty('暂无记录');
    return `<div class="table-scroll"><table><thead><tr>${columns.map(c=>`<th>${esc(c[1])}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${columns.map(([key,,format])=>`<td>${esc(format?format(row[key],row):row[key])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }
  function credentials(prefix, kind) {
    const accounts = data.bank.accounts.filter(a=>a.kind===kind);
    if (!accounts.length) return empty('请先在银行创建对应角色的账户');
    return `<div class="inline">${select(prefix+'-name','选择教学账户','name',accounts.map(a=>option(a.name,a.name+(a.active?'':' · 已冻结'))).join(''))}${field(prefix+'-password','账户密码','password','DemoCash2026!','password')}</div><p class="hint">示例账户预填教学密码。自建账户请改用自己的密码；不涉及真实资金。</p>`;
  }
  function renderBank() {
    const body = $('#bank-body');
    $('#bank-tabs').innerHTML = ['银行','付款人','收款人','验证与边界'].map(t=>`<button data-bank-tab="${t}" class="${ui.bankTab===t?'active':''}">${t}</button>`).join('');
    body.innerHTML = ({'银行':renderAdmin,'付款人':renderPayer,'收款人':renderMerchant,'验证与边界':renderVerification}[ui.bankTab])();
    restore(body);
    if (ui.bankTab === '付款人') renderPayerDetail();
  }
  function renderAdmin() {
    const b = data.bank;
    return `<div class="section-head"><div><h2>账户管理</h2><p>本页直接操作实际教学账户与 SQLite 状态</p></div><button class="subtle" data-refresh>刷新数据 ↻</button></div>
      <div class="metrics"><div class="metric"><strong>${b.issuance.filter(x=>x.state==='SIGNED').length}</strong><small>已签发现金</small></div><div class="metric"><strong>${b.deposits.length}</strong><small>首次兑付</small></div><div class="metric"><strong>${b.evidence.length}</strong><small>双花证据</small></div></div>
      <div class="table-scroll"><table><thead><tr><th>账户</th><th>角色</th><th>实验余额</th><th>状态</th><th>教学管理员</th></tr></thead><tbody>${b.accounts.map(a=>`<tr><td>${esc(a.name)}</td><td>${a.kind==='payer'?'付款人':'收款商户'}</td><td>${a.balance}</td><td>${a.active?'● 启用':'○ 冻结'}</td><td><button class="subtle" data-freeze="${esc(a.name)}" data-active="${a.active?'false':'true'}">${a.active?'冻结':'解冻'}</button></td></tr>`).join('')}</tbody></table></div>
      <details><summary>＋ 创建教学账户</summary><form data-command="account_create"><div class="inline">${field('new-name','账户名','name')}${field('new-password','初始密码（8–128字符）','password','','password')}${select('new-kind','账户类型','kind',option('payer','付款人 · 初始100')+option('merchant','商户 · 初始0'))}${button('创建账户','account_create','',true)}</div></form></details>
      <details><summary>查看银行公钥 · RSA 2048 已生成</summary><pre>${json(data.public)}</pre><p class="hint">私钥、密码散列、身份分片和盲因子不会发送到浏览器。密钥禁止覆盖重用。</p></details>
      <details open><summary>发行记录 · 与存款记录隔离</summary>${table(b.issuance,[['id','取款编号',short],['owner','取款账户'],['state','抽查状态'],['survivor','保留索引'],['created','时间']])}<p class="hint">此表没有最终现金序列号，正常存款无法用序列号反查取款账户。</p></details>
      <details open><summary>银行存款记录</summary>${table(b.deposits,[['serial','现金序列号',short],['merchant','兑付商户'],['created','时间']])}</details>
      <details open><summary>双花证据与身份恢复</summary>${table(b.evidence,[['serial','现金序列号',short],['status','验证结果'],['names','恢复账户',v=>v.join('、')||'无法恢复'],['positions','挑战不同的位置']])}</details>
      <p class="hint">账户冻结与角色切换用于教学观察，不是生产级权限管理。银行清算在数据库事务中完成，重复凭证不会重复加余额。</p>`;
  }
  function renderPayer() {
    return `<div class="section-head"><div><h2>付款人钱包</h2><p>候选生成 → 抽查 → 盲签与去盲 → 回应商户</p></div><button class="subtle" data-bank-tab="收款人">切换收款人 →</button></div><form id="payer-form" data-command="prepare">${credentials('payer','payer')}
      <div class="inline">${select('payer-n','候选数量 N','n',[2,4,8,16,32,64].map(n=>option(n)).join(''))}${select('payer-t','挑战位数 t','t',[8,16,32,64,128].map(n=>option(n)).join(''))}${button('① 生成候选并盲化','prepare','',true)}</div><p class="hint" id="probability"></p><div id="payer-detail"></div></form>`;
  }
  function payerSelected() {
    const name = $('#payer-name')?.value;
    const entries = data.wallets[name] || [];
    return {name, entries, entry:entries.find(e=>e.id===($('#payer-wid')?.value || ui.fields['payer-wid'])) || entries[entries.length-1]};
  }
  function renderPayerDetail() {
    const zone = $('#payer-detail'); if (!zone) return;
    remember(zone);
    const {name, entries} = payerSelected();
    const a = data.bank.accounts.find(a=>a.name===name);
    let chosen = entries.find(e=>e.id===ui.fields['payer-wid']) || entries[entries.length-1];
    if (!chosen) {zone.innerHTML = empty('钱包为空。先生成一组候选电子现金。'); probability(); return;}
    ui.fields['payer-wid'] = chosen.id;
    const state = chosen.state;
    const payments = Object.entries(data.payments).flatMap(([merchant,list])=>list.filter(q=>q.state==='CHALLENGED' && q.request.cash.coin.serial===chosen.cash?.coin.serial).map(q=>({...q,merchant})));
    zone.innerHTML = `<div class="metrics"><div class="metric"><strong>${a?.balance ?? '—'}</strong><small>账户可用余额</small></div><div class="metric"><strong>${entries.filter(e=>e.state==='READY').length}</strong><small>未支付现金</small></div><div class="metric"><strong>10</strong><small>单枚固定面额</small></div></div>
      ${select('payer-wid','选择钱包条目','wid',entries.map(e=>option(e.id,short(e.id)+' · '+e.state)).join(''))}
      <div class="wallet-row"><div class="wallet-heading"><h3>当前现金状态</h3>${tag(state)}</div>
      <div class="steps"><span class="done">生成 / 盲化</span><span class="${state!=='PREPARED'?'done':''}">抽查 / 预扣</span><span class="${['READY','SPENT'].includes(state)?'done':''}">盲签 / 去盲</span><span class="${state==='SPENT'?'done':''}">挑战响应</span></div>
      ${state==='PREPARED'?`<p class="hint">已生成 ${chosen.n} 组独立候选与盲因子。提交后银行随机保留一枚，预扣10实验单位。</p>${button('② 提交盲化值，接收随机抽查','submit','',true)}`:''}
      ${state==='CHALLENGED'?`<p class="hint">银行保留候选索引 <strong>${chosen.survivor}</strong>，需打开其余 ${chosen.n-1} 枚。抽查通过才会签名；去盲后立即检验签名。</p><div class="actions">${button('③ 回应抽查、盲签并去盲','issue','',true)}${button('取消并退还预扣金额','cancel')}</div>`:''}
      ${chosen.cash?`<p class="mono">序列号：${esc(chosen.cash.coin.serial)}</p><div class="actions"><button type="button" class="subtle" data-export-cash="${esc(chosen.id)}" data-owner="${esc(name)}">下载公共现金 JSON ↓</button><button type="button" class="subtle" data-bank-tab="收款人">让商户发起挑战 →</button></div><p class="hint">公共现金不含付款人身份。商户仅凭银行公钥验签并独立抽取挑战。</p>`:''}
      ${['READY','SPENT'].includes(state)?`<hr class="rule"><h3>回应商户随机挑战</h3>${payments.length?`${select('payer-pid','待回应挑战','pid',payments.map(q=>option(q.id,q.merchant+' · '+short(q.id))).join(''))}<p id="payer-challenge" class="challenge"></p><label class="check"><input id="payer-double" name="double" type="checkbox">显式开启双花攻击演示（可能泄露互补身份分片）</label><div class="actions">${button('④ 生成挑战响应','respond','',true)}<button type="button" class="subtle" data-bank-tab="收款人">去商户验证响应 →</button></div>`:empty('暂未收到此现金的挑战，请先切换收款人验签并发起挑战。')}`:''}</div>`;
    restore(zone); probability(); payerChallenge();
  }
  function probability() {
    const el=$('#probability'); if (!el) return;
    const n=Number($('#payer-n').value), t=Number($('#payer-t').value);
    el.textContent=`单坏候选抽查逃逸概率 1/${n}；两次独立挑战完全相同概率 2⁻${t} ≈ ${(2**-t).toExponential(2)}。`;
  }
  function payerChallenge() {
    const el=$('#payer-challenge'); if (!el) return;
    const pid=$('#payer-pid').value;
    const q=Object.values(data.payments).flat().find(q=>q.id===pid);
    el.textContent=q?.request.challenge.join('') || '';
  }
  function allCash() {return Object.entries(data.wallets).flatMap(([owner,list])=>list.filter(e=>e.cash).map(e=>({...e,owner})));}
  function renderMerchant() {
    const cash=allCash();
    return `<div class="section-head"><div><h2>收款人离线终端</h2><p>验签与挑战 → 离线验收 → 稍后银行清算</p></div><button class="subtle" data-bank-tab="付款人">切换付款人 →</button></div>
      <form id="merchant-form" data-command="offer">${credentials('merchant','merchant')}
      ${cash.length?`<div class="inline">${select('merchant-coin','付款人送来的公共现金','coin',cash.map(c=>option(c.owner+':'+c.id,c.owner+' / '+short(c.cash.coin.serial)+' · '+c.state)).join(''))}${button('① 验签并生成独立随机挑战','offer','',true)}</div>`:empty('暂无可支付现金，请先由付款人完成取款和去盲。')}
      <details><summary>导入公共现金 JSON · 可验证篡改或伪造现金</summary><label>选择文件（最大100KB）<input id="cash-file" type="file" accept="application/json,.json"></label><label>公共现金内容<textarea id="import-cash" name="cash" rows="4" maxlength="100000" placeholder="粘贴 cash.json 内容"></textarea></label><div class="actions">${button('导入验签并挑战','import_cash')}${cash.length?button('验证伪造签名应被拒绝','verify_forgery'):''}</div></details>
      <div id="merchant-payments"></div></form>`;
  }
  function renderMerchantPayments() {
    const zone=$('#merchant-payments'); if(!zone)return;
    const name=$('#merchant-name').value, payments=data.payments[name]||[];
    const a=data.bank.accounts.find(a=>a.name===name);
    zone.innerHTML=`<div class="metrics"><div class="metric"><strong>${a?.balance??'—'}</strong><small>商户已清算余额</small></div><div class="metric"><strong>${payments.length}</strong><small>独立支付挑战</small></div><div class="metric"><strong>${payments.filter(q=>q.state==='ACCEPTED').length}</strong><small>已验收待存款</small></div></div><h3>本商户支付与清算记录</h3>${payments.length?payments.slice().reverse().map(q=>`<div class="receipt"><div class="wallet-heading"><span class="mono">${esc(short(q.id))} · ${esc(short(q.request.cash.coin.serial))}</span>${tag(q.state)}</div><p>独立随机挑战 · ${q.request.challenge.length} 位</p><div class="challenge">${q.request.challenge.join('')}</div>
      ${q.state==='CHALLENGED'?`<p class="hint">${q.has_response?'付款人已回应，可执行离线承诺校验。':'等待付款人回应；此阶段不查询银行是否已兑付。'}</p><div class="actions">${q.has_response?button('② 离线验证响应并验收','accept',`data-pid="${esc(q.id)}"`,true):`<button type="button" class="button" data-respond-to="${esc(q.id)}">去付款人回应 →</button>`}</div>`:''}
      ${q.transcript?`<div class="actions">${button(q.result?'再次提交同一凭证':'③ 提交银行存款','deposit',`data-pid="${esc(q.id)}"`,!q.result)}<button type="button" class="subtle" data-export-receipt="${esc(q.id)}">下载支付凭证 ↓</button></div>`:''}
      ${q.result?`<p class="${q.result.status==='CREDITED'||q.result.status==='REPLAY'?'good-result':'error-result'}">${esc(q.result.status)}${q.result.identity?' · 已恢复身份，可到银行查看对应账户':''}${q.result.status==='DUPLICATE_SAME_CHALLENGE'?' · 挑战完全相同，不能恢复身份':''}</p>`:''}</div>`).join(''):empty('暂无挑战记录，选择现金后点击上方验签按钮。')}`;
    restore(zone);
  }
  function renderVerification() {
    return `<h2>验证与安全边界</h2><p class="hint">页面按钮执行真实协议，结果来自本次会话的数据库。随机挑战始终由 secrets 生成，不提供固定挑战或随机种子。</p>
      <div class="split"><div><h3>合法支付</h3><p class="hint">付款人生成 → 提交抽查 → 盲签与去盲；商户验签挑战 → 付款人回应 → 商户离线验收 → 存款。预期付款人 −10、商户 +10。</p><h3>伪造签名</h3><p class="hint">收款人页可导入被修改的 JSON，或执行“验证伪造签名应被拒绝”。失败不会产生有效支付或入账。</p><h3>双花身份恢复</h3><p class="hint">同一现金交给 shop_a 与 shop_b；第二次回应显式勾选攻击开关。两商户均可离线验收，银行只兑付一次；挑战不同的位置恢复互补分片及对应账户。</p></div><div><h3>相同挑战的概率边界</h3><p class="hint">t 位独立挑战完全相同概率为 2⁻ᵗ。此时第二次存款仍被拒绝，但没有互补响应，不能恢复身份。重复提交同一凭证是幂等重放，不等同于新支付。</p><h3>信任边界</h3><p class="hint">教学 RSA 盲签并非生产支付标准；同机钱包和角色切换不构成权限隔离。商户离线收款不能保证未被双花，身份恢复发生在银行事后清算。数据库用事务与唯一约束防止并发双兑付。</p><h3>真实记录</h3><p class="hint">发行表不存最终序列号；存款表不保存取款账户。可在银行页分别查看，不用在线序列号查询代替商户离线验证。</p></div></div><div class="actions"><button class="button" data-bank-tab="付款人">开始取款实验 →</button><button class="button" data-bank-tab="银行">查看实际记录 →</button></div>`;
  }
  function topology(result) {
    if (!result) return empty('尚未建立本次实验网络。运行后显示真实发现列表中的节点状态。');
    const peers=result.after_offline;
    const positions=peers.map((p,i)=>{const a=i*2.399963;const r=30+Math.sqrt(i/100)*105;return {id:p.id,x:300+Math.cos(a)*r*1.8,y:130+Math.sin(a)*r,active:p.active};});
    return `<svg class="network-svg" viewBox="0 0 600 270" role="img" aria-label="本次发现节点的活跃状态分布"><g>${positions.map(p=>`<line x1="300" y1="130" x2="${p.x}" y2="${p.y}" stroke="#16525a" opacity=".32"/>`).join('')}${positions.map(p=>`<circle cx="${p.x}" cy="${p.y}" r="${p.active?2.8:3.5}" fill="${p.active?'#51dcd8':'#be8e70'}"><title>节点 ${p.id} · ${p.active?'活跃':'已关闭'}</title></circle>`).join('')}<circle cx="300" cy="130" r="7" fill="none" stroke="#ddffff"/><text x="315" y="135" fill="#c8e5e7" font-size="11">新节点</text></g></svg><p class="network-caption">点颜色来自两轮心跳后的实际节点表；连线仅作状态分布示意，不表示实际连接拓扑。</p>`;
  }
  function renderNodes() {
    const body=$('#node-body'); remember(body);
    $('#node-tabs').innerHTML=['实验控制台','活跃节点','密码学校验','批量实测'].map(t=>`<button data-node-tab="${t}" class="${ui.nodeTab===t?'active':''}">${t}</button>`).join('');
    body.innerHTML=({'实验控制台':renderConsole,'活跃节点':renderPeers,'密码学校验':renderCrypto,'批量实测':renderBench}[ui.nodeTab])();restore(body);
    if(ui.nodeTab==='批量实测') plotBench();
    if(ui.nodeTab==='实验控制台'){const sequential=$('#node-optimized').value==='false';$('#node-workers').disabled=sequential;if(sequential)$('#node-workers').value='1';}
  }
  function renderConsole() {
    const r=data.p2p, s=r?.sync;
    return `<form data-command="p2p_run"><div class="inline">${select('node-size','每个区块大小','size',[65536,262144,1048576].map(n=>option(n,n/1024+' KiB')).join(''))}${select('node-count','同步区块数量','count',[1,2,3,10].map(n=>option(n,n+' 个区块')).join(''))}${select('node-profile','网络条件','profile',Object.entries(profiles).map(([k,v])=>option(k,v)).join(''))}${select('node-optimized','同步策略','optimized',option('true','多源并发＋断点续传')+option('false','顺序基线＋失败切换'))}${select('node-workers','并行下载数','workers',[1,2,3,4,6,8].map(n=>option(n)).join(''))}${button('运行模拟 ↗','p2p_run','',true)}</div></form>
      <p class="hint">运行时真实建立100个已有节点与1个新节点的本机 TCP 监听。网络延迟、限速和故障为应用层教学注入；耗时是实际测量。未运行时不会显示预录结果。</p>
      <div class="split wide"><div><h3>网络节点状态</h3>${topology(r)}</div><aside class="status-strip"><div><strong>${r?.listeners??'—'}</strong><small>实际监听节点</small></div><div><strong>${s?.height??'—'}</strong><small>同步区块高度</small></div><div><strong>${s?(s.elapsed_s*1000).toFixed(1)+' ms':'—'}</strong><small>同步总耗时</small></div></aside></div>
      ${r?`<div class="metrics"><div class="metric"><strong>${s.throughput_mib_s.toFixed(2)}</strong><small>有效吞吐 MiB/s</small></div><div class="metric"><strong>${(100*s.transfer_efficiency).toFixed(1)}%</strong><small>传输效率</small></div><div class="metric"><strong>${s.queue_p95_ms.toFixed(2)} ms</strong><small>数据排队 P95</small></div><div class="metric"><strong>${s.retries} / ${s.timeouts} / ${s.busy}</strong><small>重试 / 超时 / BUSY</small></div></div><div class="section-head"><h3>本次执行状态</h3><button class="subtle" data-export-run>下载实际运行 JSON ↓</button></div>${r.states.map(s=>`<div class="run-state">${esc(s)}</div>`).join('')}<details><summary>故障与重试记录（${r.events.length}）</summary><pre>${json(r.events)}</pre></details>`:''}`;
  }
  function renderPeers() {
    const r=data.p2p;
    return `<h2>节点加入、发现与列表维护</h2><p class="hint">新节点从3个种子开始 HELLO 握手，传播邻居并主动探测。30秒 TTL，两轮心跳失败标记失活。下表来自本次实际监听的节点，不是静态设计图。</p>${r?`<div class="metrics"><div class="metric"><strong>${r.discovery.active}</strong><small>初次发现活跃节点</small></div><div class="metric"><strong>${(r.discovery.elapsed_s*1000).toFixed(1)} ms</strong><small>实际发现耗时</small></div><div class="metric"><strong>${r.active_after_offline}</strong><small>关闭5个节点、维护后</small></div></div>${table(r.after_offline,[['id','节点'],['port','本机端口'],['active','活跃',v=>v?'是':'否'],['failures','连续失败'],['rtt_ms','响应毫秒',v=>Number(v).toFixed(2)]])}`:empty('先运行一次实验，随后可以查看100个已有节点的实际响应与状态。')}`;
  }
  function renderCrypto() {
    const r=data.p2p;
    return `<h2>Bitcoin Script 与区块完整性校验</h2><p class="hint">执行真实旧式 P2PKH 脚本，使用 secp256k1 ECDSA 和 SIGHASH_ALL。区块接收依次验证传输校验和、前区块哈希、Merkle 根、UTXO 与金额守恒；整块通过后原子更新状态。</p><pre>scriptSig: &lt;DER signature + 01&gt; &lt;compressed public key&gt;\nscriptPubKey: OP_DUP OP_HASH160 &lt;pubkey hash&gt; OP_EQUALVERIFY OP_CHECKSIG</pre>${r?`<details open><summary>本次实际交易脚本</summary><h3>锁定脚本 HEX</h3><pre>${esc(r.sample.locking_hex)}</pre><h3>解锁脚本 HEX</h3><pre>${esc(r.sample.unlocking_hex)}</pre></details><details open><summary>本次接收区块的校验清单</summary><pre>${json(r.manifest)}</pre></details>`:empty('运行实验后，显示本次真实脚本字节和校验清单。')}<p class="hint danger">自定义教学区块，非比特币主网区块；不包含挖矿或完整共识。每块固定4笔交易，大小由已认证填充数据调整，不能据此推断主网交易扩展性。</p>`;
  }
  function renderBench() {
    const b=data.bench;
    return `<div class="section-head"><div><h2>已有批量实测对比</h2><p>历史测量与本次运行分开显示；不冒充当前运行数据</p></div><button class="subtle" data-export-bench>下载分组均值 ↓</button></div><div class="inline">${select('bench-profile','网络条件','profile',Object.entries(profiles).map(([k,v])=>option(k,v)).join(''))}${select('bench-size','区块大小','size',[65536,262144,1048576].map(n=>option(n,n/1024+' KiB')).join(''))}</div><div id="bench-plot"></div><p class="hint">${b?.count??0} 次既有同步测量，图表显示分组平均值。数据仅代表本机与明确的网络模型。${esc(b?.started??'')}</p>`;
  }
  function plotBench() {
    const zone=$('#bench-plot');if(!zone)return;
    const rows=(data.bench?.rows||[]).filter(r=>r.profile===$('#bench-profile').value&&r.size===Number($('#bench-size').value)).sort((a,b)=>a.blocks-b.blocks||a.strategy.localeCompare(b.strategy));
    if(!rows.length){zone.innerHTML=empty('没有对应的历史测量');return;}
    const max=Math.max(...rows.map(r=>r.elapsed)), x=n=>50+([1,2,3,10].indexOf(n))*155, y=s=>180-s/max*145;
    zone.innerHTML=`<svg class="plot" viewBox="0 0 560 225" role="img" aria-label="不同同步数量与策略的平均耗时"><line x1="50" y1="180" x2="525" y2="180" stroke="#33575e"/>${['baseline','optimized'].map((strategy,i)=>{const sub=rows.filter(r=>r.strategy===strategy).sort((a,b)=>a.blocks-b.blocks);return `<polyline points="${sub.map(r=>x(r.blocks)+','+y(r.elapsed)).join(' ')}" fill="none" stroke="${i?'#00d7df':'#aeb6bb'}" stroke-width="2"/>${sub.map(r=>`<circle cx="${x(r.blocks)}" cy="${y(r.elapsed)}" r="4" fill="${i?'#00d7df':'#aeb6bb'}"><title>${r.blocks}块 · ${strategy} · ${r.elapsed.toFixed(4)}秒</title></circle>`).join('')}`;}).join('')}${[1,2,3,10].map(n=>`<text x="${x(n)}" y="205" fill="#85a3a9" font-size="11">${n}块</text>`).join('')}<text x="50" y="18" fill="#85a3a9" font-size="10">平均总耗时 · 最高 ${max.toFixed(3)}秒</text></svg><p class="hint">青色：优化方案　灰色：顺序基线</p>${table(rows,[['blocks','区块数'],['strategy','策略'],['elapsed','平均秒',v=>v.toFixed(4)],['std','标准差秒',v=>v.toFixed(4)],['efficiency','传输效率',v=>(100*v).toFixed(1)+'%'],['queue','排队P95毫秒',v=>v.toFixed(2)]])}`;
  }
  function renderCourse() {
    const body=$('#course-body');
    const addQuestion=`<details><summary>＋ 录入老师布置的题目</summary><form data-command="question_add"><label>粘贴老师的原题<textarea id="teacher-question" name="question" rows="4" maxlength="20000" required placeholder="粘贴实际布置的题目，不自动生成题目…"></textarea></label><div class="actions">${button('录入题目','question_add','',true)}</div></form></details>`;
    if(!data.questions.length){body.innerHTML=`<div class="course-layout"><aside class="question-nav"><h3>题目导航</h3><p class="hint">暂无老师题目</p></aside><div class="answer-pane"><h2>题目待录入</h2><p class="hint">粘贴老师题目后，按问题001、002、003…排列，左侧选择，右侧直接填写答案。</p>${addQuestion}<p class="hint">本次会话中录入与作答可下载留存，不自动编造老师的题目。</p></div></div>`;restore(body);return;}
    if(!data.questions.some(q=>q.id===ui.qid))ui.qid=data.questions[0].id;
    const q=data.questions.find(q=>q.id===ui.qid);
    const answer=ui.answers[q.id]??q.answer;
    body.innerHTML=`<div class="course-layout"><aside class="question-nav"><h3>题目导航</h3><input id="question-search" aria-label="搜索老师题目" placeholder="搜索题目"><div id="question-list"></div></aside><div class="answer-pane"><small>问题${String(q.id).padStart(3,'0')}</small><h2>题目</h2><div class="question-text">${esc(q.question)}</div><hr class="rule"><h2>我的答案</h2><form data-command="answer_save"><textarea id="course-answer" name="answer" aria-label="我的答案" maxlength="100000" placeholder="在这里填写你的答案…">${esc(answer)}</textarea><div class="actions">${button('保存答案','answer_save','',true)}<button type="button" class="subtle" data-export-answer>下载当前答案 ↓</button><button type="button" class="subtle" data-export-course>下载全部题目与已保存答案 ↓</button></div></form><p class="hint">保存在本次会话。下载后可长期留存；刷新或服务重启可能重置会话。老师题目不分状态类别。</p>${addQuestion}</div></div>`;
    restore(body);$('#course-answer').value=answer;renderQuestionList();
  }
  function renderQuestionList(){
    const text=$('#question-search')?.value.toLowerCase()||'';
    $('#question-list').innerHTML=data.questions.filter(q=>(q.question+String(q.id).padStart(3,'0')).toLowerCase().includes(text)).map(q=>`<button data-question="${q.id}" class="${q.id===ui.qid?'active':''}">问题${String(q.id).padStart(3,'0')}</button>`).join('')||empty('无匹配题目');
  }
  function showNotice(message, type='success') {
    const notice=$('#notice');notice.hidden=false;notice.className='notice '+type;notice.textContent=message;
  }
  function submit(action,payload) {
    if(request)return;
    request={id:crypto.randomUUID(),action,payload};
    $$('[data-command],button[type=submit],[data-freeze],[data-refresh]').forEach(b=>b.disabled=true);
    showNotice(action==='p2p_run'?'正在建立101个节点、传输区块并执行真实校验，请稍候…':'正在执行协议并写入实验状态…','busy');
    sender('action',request);
  }
  function download(value,name){const blob=new Blob([JSON.stringify(value,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;root.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  root.addEventListener('submit',event=>{
    event.preventDefault();const form=event.target;const b=event.submitter;const command=b?.dataset.command||form.dataset.command;if(!command)return;
    const p=Object.fromEntries([...new FormData(form)].filter(([,v])=>typeof v==='string'));
    if(b?.dataset.pid)p.pid=b.dataset.pid;
    for(const key of ['n','t','size','count','workers'])if(key in p)p[key]=Number(p[key]);
    if('optimized'in p){p.optimized=p.optimized==='true';if(!p.optimized)p.workers=1;}
    if(command==='respond'){p.double=!!$('#payer-double')?.checked;p.merchant=Object.entries(data.payments).find(([,list])=>list.some(q=>q.id===p.pid))?.[0];}
    if(['offer','verify_forgery'].includes(command)){[p.owner,p.wid]=(p.coin||'').split(':');}
    if(command==='answer_save')p.qid=ui.qid;
    submit(command,p);
  });
  root.addEventListener('input',event=>{
    const el=event.target;
    if(el.id==='course-answer')ui.answers[ui.qid]=el.value;
    if(el.id==='question-search')renderQuestionList();
  });
  root.addEventListener('change',async event=>{
    const el=event.target;remember(root);
    if(el.id==='payer-name'||el.id==='payer-wid'){ui.fields['payer-double']=false;if($('#payer-double'))$('#payer-double').checked=false;renderPayerDetail();}
    if(el.id==='payer-pid'){ui.fields['payer-double']=false;if($('#payer-double'))$('#payer-double').checked=false;}
    if(el.id==='merchant-name')renderMerchantPayments();
    if(el.id==='payer-n'||el.id==='payer-t')probability();
    if(el.id==='payer-pid')payerChallenge();
    if(el.id==='bench-profile'||el.id==='bench-size')plotBench();
    if(el.id==='node-optimized'){$('#node-workers').disabled=el.value==='false';if(el.value==='false')$('#node-workers').value='1';}
    if(el.id==='cash-file'&&el.files[0]){
      if(el.files[0].size>100000){showNotice('文件超过100KB','error');el.value='';return;}
      $('#import-cash').value=await el.files[0].text();
    }
  });
  root.addEventListener('click',event=>{
    if(event.target.closest('#notice')&&!request){$('#notice').hidden=true;return;}
    const b=event.target.closest('button');if(!b)return;
    if(b.dataset.goto!==undefined){void go(Number(b.dataset.goto),'nav');return;}
    if(b.dataset.bankTab){remember(root);ui.bankTab=b.dataset.bankTab;renderBank();if(ui.bankTab==='收款人')renderMerchantPayments();$('#bank-body').scrollTop=0;}
    if(b.dataset.nodeTab){ui.nodeTab=b.dataset.nodeTab;renderNodes();$('#node-body').scrollTop=0;}
    if(b.dataset.question){remember(root);ui.qid=Number(b.dataset.question);renderCourse();}
    if(b.hasAttribute('data-refresh'))submit('refresh',{});
    if(b.dataset.freeze)submit('account_active',{name:b.dataset.freeze,active:b.dataset.active==='true'});
    if(b.dataset.respondTo){ui.fields['payer-pid']=b.dataset.respondTo;const q=Object.values(data.payments).flat().find(q=>q.id===b.dataset.respondTo);const c=allCash().find(c=>c.cash.coin.serial===q.request.cash.coin.serial);if(c){ui.fields['payer-name']=c.owner;ui.fields['payer-wid']=c.id;}ui.bankTab='付款人';renderBank();}
    if(b.dataset.exportCash)download(data.wallets[b.dataset.owner].find(w=>w.id===b.dataset.exportCash).cash,'cash.json');
    if(b.dataset.exportReceipt)download(Object.values(data.payments).flat().find(q=>q.id===b.dataset.exportReceipt).transcript,'transcript.json');
    if(b.hasAttribute('data-export-run')&&data.p2p)download(data.p2p,'single_run.json');
    if(b.hasAttribute('data-export-bench'))download(data.bench,'batch_means.json');
    if(b.hasAttribute('data-export-course'))download(data.questions,'coursework.json');
    if(b.hasAttribute('data-export-answer'))download({...data.questions.find(q=>q.id===ui.qid),answer:$('#course-answer').value},`问题${String(ui.qid).padStart(3,'0')}.json`);
  });
  function nav(index){
    targetNav=index;
    $$('[data-goto]').forEach(b=>{if(Number(b.dataset.goto)===index)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
    const tab=$(`.main-nav [data-goto="${index}"]`), line=$('.nav-underline');line.style.width=tab.offsetWidth+'px';line.style.transform=`translateX(${tab.offsetLeft}px)`;
    $('#screen-counter').textContent=String(index+1).padStart(2,'0')+' / 04';$('#screen-hint').textContent=index?'内容区可滚动 · 屏幕边缘切屏':'滚动探索';$('#previous').disabled=index===0;$('#next').disabled=index===3;
  }
  function settle(){scenes.forEach((s,i)=>{s.classList.toggle('is-active',i===ui.current);s.classList.remove('moving');s.inert=i!==ui.current;s.setAttribute('aria-hidden',String(i!==ui.current));s.style.zIndex='';});root.dataset.currentScene=sceneIds[ui.current];nav(ui.current);}
  async function go(index, source='nav'){
    index=YinbiMotion.clamp(index,0,3);if(moving){if(source==='nav')pending=index;return;}if(index===ui.current)return;
    if(!request)$('#notice').hidden=true;
    moving=true;root.dataset.transitioning='true';
    const from=scenes[ui.current],to=scenes[index],direction=Math.sign(index-ui.current);let running=[];
    try{
      if(!imageReady){await Promise.all([...root.querySelectorAll('img')].map(img=>img.decode().catch(()=>{})));imageReady=true;}
      from.classList.add('moving');to.classList.add('moving');from.inert=true;to.inert=true;from.style.zIndex='1';to.style.zIndex='2';
      const timing={duration:media.matches?0:820,easing:'cubic-bezier(.65,0,.35,1)',fill:'both'};
      const animate=(el,frames)=>{const a=el.animate(frames,timing);animations.add(a);running.push(a);};
      animate(from,[{transform:'translate3d(0,0,0) scale(1)',opacity:1},{transform:`translate3d(0,${-direction*9}%,-70px) scale(.955)`,opacity:.18}]);
      animate(to,[{transform:`translate3d(0,${direction*101}%,0) scale(1.025)`},{transform:'translate3d(0,0,0) scale(1)'}]);
      const visual=to.querySelector('.hero-art,.home-visual');if(visual)animate(visual,[{transform:`translateY(${-direction*3}%) scale(1.03)`},{transform:'translateY(0) scale(1)'}]);
      const foreground=to.querySelector('.work-body,.home-entries');if(foreground)animate(foreground,[{transform:`translateY(${direction*3}%)`,opacity:.3},{transform:'translateY(0)',opacity:1}]);
      nav(index);await Promise.all(running.map(a=>a.finished));ui.current=index;
    }catch(_){/* A cancelled animation settles on the last complete scene. */}
    finally{settle();running.forEach(a=>{a.cancel();animations.delete(a);});moving=false;root.dataset.transitioning='false';if(pending!==null){const next=pending;pending=null;void go(next,'nav');}}
  }
  $('#previous').onclick=()=>go(ui.current-1);$('#next').onclick=()=>go(ui.current+1);
  root.addEventListener('wheel',e=>{if(e.ctrlKey||e.metaKey||e.target.closest('input,select,textarea,[data-scroll]'))return;const {x,y}=YinbiMotion.wheelPixels(e,root.clientHeight);if(!y||Math.abs(x)>Math.abs(y))return;e.preventDefault();const d=gate.observe(y,performance.now(),moving);if(d)void go(ui.current+d,'wheel');},{passive:false});
  root.addEventListener('keydown',e=>{if(e.ctrlKey||e.metaKey||e.altKey||e.repeat||e.target.closest('input,textarea,select'))return;let next;if(['ArrowDown','PageDown','ArrowRight'].includes(e.key))next=ui.current+1;if(['ArrowUp','PageUp','ArrowLeft'].includes(e.key))next=ui.current-1;if(e.key==='Home')next=0;if(e.key==='End')next=3;if(next!==undefined){e.preventDefault();if(!moving)void go(next,'keyboard');}});
  root.addEventListener('touchstart',e=>{if(e.touches.length!==1||e.target.closest('[data-scroll],input,textarea,select')){touch=null;return;}touch={x:e.touches[0].clientX,y:e.touches[0].clientY,at:performance.now(),blocked:moving};},{passive:true});
  root.addEventListener('touchmove',e=>{if(touch&&e.touches.length===1&&Math.abs(e.touches[0].clientY-touch.y)>Math.abs(e.touches[0].clientX-touch.x))e.preventDefault();},{passive:false});
  root.addEventListener('touchend',e=>{if(!touch)return;const t=touch;touch=null;const p=e.changedTouches[0];if(!p||t.blocked||moving||performance.now()-t.at>1200)return;const y=p.clientY-t.y,x=p.clientX-t.x;if(Math.abs(y)>46&&Math.abs(y)>Math.abs(x)*1.1)void go(ui.current+(y<0?1:-1),'touch');},{passive:true});
  root.addEventListener('touchcancel',()=>touch=null);
  const observer=new ResizeObserver(()=>nav(targetNav));
  const finishAnimations=()=>{if(media.matches)animations.forEach(a=>{try{a.finish();}catch(_){}});};
  function update(next,emit){
    remember(root);data=next;sender=emit;
    if(request&&data.notice?.id===request.id){
      if(data.notice.ok&&data.notice.wallet_id)ui.fields['payer-wid']=data.notice.wallet_id;
      if(data.notice.ok&&data.notice.question_id){ui.qid=data.notice.question_id;ui.fields['teacher-question']='';}
      if(request.action==='respond')ui.fields['payer-double']=false;
      request=null;showNotice(data.notice.message,data.notice.ok?'success':'error');
    }
    if(!imageReady){$('.home-image').src=data.assets+'home.png';$$('[data-asset]').forEach(img=>img.src=data.assets+img.dataset.asset);}
    renderBank();if(ui.bankTab==='收款人')renderMerchantPayments();renderNodes();renderCourse();observer.observe(root);media.addEventListener('change',finishAnimations);
    nav(targetNav);root.dataset.ready='true';
  }
  ui.fields['payer-n']='16';ui.fields['payer-t']='32';ui.fields['node-size']='262144';ui.fields['node-count']='3';ui.fields['node-workers']='4';
  settle();root.dataset.transitioning='false';root.focus({preventScroll:true});
  return {update,cleanup(){observer.disconnect();media.removeEventListener('change',finishAnimations);}};
}

export default function(component) {
  const {parentElement,data,setTriggerValue}=component;
  let runtime=parentElement.__yinbiRuntime;
  if(!runtime){runtime=mountLab(parentElement.querySelector('#live-app'),data,setTriggerValue);parentElement.__yinbiRuntime=runtime;}
  runtime.update(data,setTriggerValue);
  return ()=>runtime.cleanup();
}
