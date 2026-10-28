# 隐币实验室

在线演示：[打开隐币实验室](https://yuping.streamlit.app/)。源码：[Yang-yaping/ZY](https://github.com/Yang-yaping/ZY)。

同一套可操作的四屏网站：课程首页、线上银行、节点模拟器、课程作业。保留已确认的青绿色玻璃图片作为视觉素材，操作区使用真实 HTML 表单、实时表格与校验结果。全部操作在新界面内完成，不跳转旧工作台，不用静态图片模拟实验结果。

- **离线电子现金**：保留原来的总览、银行、付款人、收款人、场景与验收。支持盲RSA、cut-and-choose、离线随机挑战、SQLite原子存款与双花身份恢复。
- **P2P 网络与区块同步**：新增101节点本机TCP实验、1/2/3/10区块同步、网络异常、策略对比、Bitcoin Script P2PKH、Merkle与UTXO校验，以及已实际运行的批量数据。

切换实验时，电子现金账户与钱包保持在同一访客沙箱中；P2P结果也会保留。两个实验独立使用各自的数据和状态。P2P演示没有将原来的银行式离线电子现金改成公链。

## 全屏交互

- 滚轮、触控板上下滑动：每个手势切换一屏，惯性输入不会继续跳屏。
- 顶部导航、右侧圆点：可从任意屏直接切换，当前项同步高亮。
- 键盘方向键、Page Up/Down、空格：前后切换；Home/End：第一屏/最后一屏。
- 手机单指纵向滑动：前后切换；双指缩放与原图查看区域保留原生操作。
- 所有切换共用约 820ms 的层叠转场：旧屏后退缩小，新屏进入，图片与前景轻微视差。系统开启“减少动态效果”时立即切换。

银行内直接切换“银行 / 付款人 / 收款人 / 验证与边界”，按钮调用原有 Python 协议和 SQLite。页面可生成候选、回应 N−1 抽查、盲签去盲、产生商户随机挑战、验证响应和提交存款；支持取消退额、账户冻结、导入伪造现金验证、公共现金与凭证下载。第二次支付默认被钱包阻止，必须显式勾选教学攻击开关；响应后该开关自动关闭。发行、存款与双花身份恢复分别展示。

节点页直接选择区块大小、同步数量、网络条件、策略和并行数，运行真实 101 节点本机 TCP 实验，并显示本次发现表、耗时、重试、吞吐、脚本字节与校验清单。历史360次批量测量单独标注，支持筛选对比。网络图的颜色来自实测活跃表，连线只是布局示意，不冒充实际连接拓扑。

课程作业保持左侧“问题001、002…”、右侧题目与答案。不设状态分类，可直接粘贴老师的原题、作答、保存及下载。源文件 `content/coursework.json` 默认为空，不编造真实题目；可写入 `[{"id":1,"question":"老师布置的题目","answer":"我的答案"}]` 作为长期展示内容。页面录入与编辑保存在当前会话，刷新或重启可能重置，请下载留存。

鼠标在页面边缘或标题区域可滚轮切屏；内容区保留原生滚动，避免填写或查看长表格时误跳屏。导航始终可直达任意页面，实验状态在同一会话中保持。触控滑动在标题或页面边缘触发，表单和长内容区可以正常操作。

技术上继续使用 Streamlit（1.66.1及以上），通过原生 Components v2 的会话双向通道连接自定义界面和 Python。无需额外 REST 服务、iframe 或外部动画 CDN。图片文件字节不变，校验清单在 `static/scenes/manifest.json`。浏览器只接收公共现金、公钥和实验结果，私钥、密码散列、钱包盲因子与未公开身份分片不发送给前端。请求具有编号去重、输入校验与执行中防连点；SQLite 原子清算仍由原协议负责。

## 本地启动

建议 Python 3.12。在文件夹内逐行运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8503
```

打开 `http://127.0.0.1:8503`。Mac 可双击 `start.command`。Windows 激活虚拟环境使用 `.venv\Scripts\activate`，其余 Python 命令相同；Windows尚未实际验证。

首次安装依赖需要联网。程序需要可供 python-bitcoinlib 加载的 OpenSSL；出现 SSL 加载错误时应配置匹配的库，不能跳过验签。停止网页服务：在启动终端按 Control+C。

默认每位访客使用独立临时沙箱，示例账户为 alice、shop_a、shop_b，示例密码 `DemoCash2026!`。仅使用虚拟信息。会话刷新或服务重启后可能重置，角色切换仅用于观察协议，不是安全权限隔离。

## 目录与源代码

```text
app.py                  统一四屏网站与兼容路由
showcase.py             默认页面入口
interactive.py          Streamlit 双向组件与会话绑定
live_lab.py             输入校验、命令去重、协议适配与公共状态快照
web/live/               可操作界面、表单、实时图表与统一转场
web/showcase/           复用的滚轮策略与上一版预览参考
static/scenes/          四张原始设计图及校验清单
coursework.py           题目文件校验及旧版参考界面
content/coursework.json 老师题目与已确认答案
cash_app.py             保留的旧控制台，用于协议回归参考
cloud_app.py            保持原线上入口，运行统一app.py
ecash/                  原电子现金协议及SQLite实现
p2p/app.py              P2P实验页面
p2p/lab/                TCP网络、发现、同步与Bitcoin Script验证
p2p/results/            原始实测CSV、公开区块、统计与图表
p2p/tools/              P2P批量复测、统计和独立夹具校验
tests/                  电子现金及跨实验导航回归测试
p2p/tests/              P2P协议、网络和页面测试
validation/             整合版实际测试输出
docs/upstream.json      原站源码对应GitHub树及文件校验记录
requirements.txt        两个实验共同的安装清单
```

交作业的源代码包括上述 Python、HTML、CSS、JavaScript 文件及所需目录，不是终端登录提示。压缩包不包括虚拟环境、运行数据库、私钥或实验报告。

## 测试与复测

```bash
python -m unittest discover -s tests -v
PYTHONPATH=p2p python -m unittest discover -s p2p/tests -v
python tests/cloud_flow.py
# 旧控制台回归（不作为新界面的浏览器验收）
python tests/ui_flow.py
python p2p/tools/validate_fixtures.py
node --test tests/motion-core.test.cjs
```

第二行的 `PYTHONPATH=p2p` 是 macOS/Linux 写法；Windows PowerShell 可先执行 `$env:PYTHONPATH="p2p"` 再执行 Python 命令。核心测试和页面导航测试分别覆盖电子现金与P2P，并检查跨页面切换不会重置钱包或混用状态。

批量P2P复测：进入 `p2p` 目录，运行 `python tools/run_experiments.py --output results_rerun`，再运行 `python tools/analyze.py --input results_rerun`。本次沿用已交付的360次同步、12次发现、24次负载测量，不将页面整合描述为新一轮批量测量。详细模型、指标和安全边界见 `p2p/README.md`。

## 线上更新

整合版保留原仓库的 `app.py`、`cloud_app.py` 和根目录 `requirements.txt` 位置。原 Streamlit 应用无论使用哪个入口均运行新的可操作界面；新增依赖由平台安装。仅上传源码和公开数据，不上传 `.venv`、`tmp`、数据库或本地配置凭据。

本版本用于更新原 `Yang-yaping/ZY` 项目。源码更新会触发已连接的Streamlit应用重新部署；线上构建状态与可用性需以实际网页验证为准。P2P演示会临时创建101个本机TCP监听；云主机若限制套接字或资源，页面会显示真实失败，不用预录数据冒充实时实验。
