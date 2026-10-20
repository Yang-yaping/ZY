# 隐币实验室：简化离线电子现金

在线演示：[打开隐币实验室](https://yuping.streamlit.app/)。示例账户为 `alice`、`shop_a`、`shop_b`，密码均为 `DemoCash2026!`。线上实际验证范围见 [ONLINE-VALIDATION.md](docs/ONLINE-VALIDATION.md)。

## 公开网页运行

本仓库同时提供本地版与在线演示入口。在线版为每位浏览器访客分配独立实验数据库，并自动建立alice、shop_a、shop_b三个示例账户，密码均为`DemoCash2026!`。每位访客分别完成三角色流程；不要跨两个独立浏览器会话做同一次实验。数据可能随新会话或服务重启重置，仅使用虚拟信息。更多说明见[部署说明](docs/DEPLOY.md)。

```sh
python -m streamlit run cloud_app.py
```

上传GitHub只完成源码托管；公开演示网址以网页托管平台实际部署成功后显示的地址为准。

三角色教学演示，不用于真实资产。

## 快速启动

需要 Python 3.10+。macOS 可双击 `start.command`，首次需网络下载依赖。或终端进入本目录：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ECASH_DATA=data python -m streamlit run app.py --server.address 127.0.0.1
```

浏览器打开 http://localhost:8501 。Windows 激活命令为 `.venv\Scripts\activate`；PowerShell 先执行 `$env:ECASH_DATA="data"`，再运行 `python -m streamlit run app.py`。
离线运行指支付协议不连接银行；首次安装软件仍需网络。依赖安装后整个演示可在断网环境运行。

## 试用

1. 银行页生成密钥。创建付款人 `alice`、商户 `shop_a` 与 `shop_b`，自行设至少8位密码。付款人获100实验单位，商户初始0。固定面额10。
2. 付款人页登录，依次点击生成候选、提交盲化值、回应抽查并去盲。N默认16，挑战位t默认32。
3. 收款人页选择 shop_a 和现金，点击验签并生成挑战。
4. 付款人页选择该现金和待回应挑战，生成响应。
5. shop_a 点击离线验收，再提交银行，显示 CREDITED。银行页观察余额和独立存款记录。
6. shop_b 对同一现金重新发起挑战。付款人明确开启双花攻击演示后回应。shop_b 仍能离线验收，存款时银行不再入账；若挑战至少一位不同，恢复 alice 的身份。
7. 伪造：导出公共现金JSON，修改 signature 为 `2`，在收款人页导入，银行验签失败。

同一付款人可生成多条钱包记录。页面不会提供固定挑战或伪随机种子。相同挑战边界用自动化测试注入，以保证可重复，不改动正式协议路径。

## 文件结构

- `app.py`：三角色界面、引导、余额和证据展示。
- `ecash/crypto.py`：RSA 教学盲签、带盐承诺、输入验证、纯离线验签和响应验证、互补分片恢复。
- `ecash/bank.py`：账户、预扣取款、抽查签发、原子清算和证据。
- `ecash/actors.py`：付款人钱包与不依赖 Bank 的商户终端。
- `ecash/storage.py`：事务、SQLite连接管理。
- `tests/`：正常、攻击、边界和并发验收。
- `docs/DESIGN.md`：协议、状态、数据库和安全边界。
- `docs/REPORT_MATERIALS.md`：对应上传DOC模板的报告素材及截图清单。

公开部署副本的 `app.py` 与 `cloud_app.py` 默认均使用访客独立在线模式；`cloud_app.py` 始终强制在线模式。通过 `start.command` 或显式设置 `ECASH_DATA=data` 运行 `app.py`，即可使用本地持久模式。本地数据位于指定目录，首次运行建立三个逻辑区域：`bank.db`、`wallets/<账户>.db`、`merchants/<商户>.db`。关停程序后换一个空目录即可开始新实验；请勿只删除银行数据库而保留旧钱包。

## 重要边界

采用 N 候选开 N−1 的单现金抽查变体，不是讲义“约一半打开、剩余签名”的逐式实现；单坏候选逃逸概率1/N，默认1/16绝不属于生产级安全。挑战识别概率为1−2^−t，二者不是同一个安全参数。带域分离的教学 RSA-FDH 盲签不等于 RFC 9474 的 RSA-PSS 盲签，不提供完整安全证明、抗侧信道或安全密钥托管。

正常现金与支付凭证不携带账户名或完整身份。银行发行表不保存最终序列号。商户协议类不访问银行；页面为方便课堂传递对象，仍在同一进程读取模拟账户列表和钱包公共现金，页面角色切换不是权限隔离。主机管理员可读取所有数据库，所以不对主机管理员承诺匿名。敏感数据和其他局限详见 DESIGN。

已安装Streamlit后，也可运行页面端到端测试：`python tests/ui_flow.py`。它使用临时数据库模拟真实组件点击，涵盖正常支付与第二商户双花存款，不改变演示数据。切换角色后需重新输入相应账户密码；查看第二商户时请选择shop_b。
