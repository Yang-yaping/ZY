# 隐币实验室

在线演示：[打开隐币实验室](https://yuping.streamlit.app/)。源码：[Yang-yaping/ZY](https://github.com/Yang-yaping/ZY)。

同一个 Streamlit 网站中的两个独立课程实验，使用侧栏“实验项目”切换。

- **离线电子现金**：保留原来的总览、银行、付款人、收款人、场景与验收。支持盲RSA、cut-and-choose、离线随机挑战、SQLite原子存款与双花身份恢复。
- **P2P 网络与区块同步**：新增101节点本机TCP实验、1/2/3/10区块同步、网络异常、策略对比、Bitcoin Script P2PKH、Merkle与UTXO校验，以及已实际运行的批量数据。

切换实验时，电子现金账户与钱包保持在同一访客沙箱中；P2P结果也会保留。两个实验独立使用各自的数据和状态。P2P演示没有将原来的银行式离线电子现金改成公链。

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
app.py                  统一侧栏与页面路由
cash_app.py             原隐币实验室电子现金页面
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

交作业的源代码是上述 `.py` 文件及目录，不是终端登录提示。压缩包不包括虚拟环境、运行数据库、私钥或实验报告。

## 测试与复测

```bash
python -m unittest discover -s tests -v
PYTHONPATH=p2p python -m unittest discover -s p2p/tests -v
python tests/ui_flow.py
python p2p/tools/validate_fixtures.py
```

第二行的 `PYTHONPATH=p2p` 是 macOS/Linux 写法；Windows PowerShell 可先执行 `$env:PYTHONPATH="p2p"` 再执行 Python 命令。核心测试和页面导航测试分别覆盖电子现金与P2P，并检查跨页面切换不会重置钱包或混用状态。

批量P2P复测：进入 `p2p` 目录，运行 `python tools/run_experiments.py --output results_rerun`，再运行 `python tools/analyze.py --input results_rerun`。本次沿用已交付的360次同步、12次发现、24次负载测量，不将页面整合描述为新一轮批量测量。详细模型、指标和安全边界见 `p2p/README.md`。

## 线上更新

整合版保留原仓库的 `app.py`、`cloud_app.py` 和根目录 `requirements.txt` 位置。原 Streamlit 应用无论使用哪个入口均运行统一工作台；新增依赖由平台安装。仅上传源码和公开数据，不上传 `.venv`、`tmp`、数据库或本地配置凭据。

本版本用于更新原 `Yang-yaping/ZY` 项目。源码更新会触发已连接的Streamlit应用重新部署；线上构建状态与可用性需以实际网页验证为准。P2P演示会临时创建101个本机TCP监听；云主机若限制套接字或资源，页面会显示真实失败，不用预录数据冒充实时实验。
