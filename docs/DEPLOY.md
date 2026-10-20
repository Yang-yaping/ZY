# 在线演示部署

公开代码不包含运行数据库、私钥、真实账户或个人报告。

在 Streamlit Community Cloud 中连接实际拥有仓库的 GitHub 账号，选择代码所在仓库、main 分支、入口 cloud_app.py，Python 版本选择3.12。requirements.txt 和 .streamlit/config.toml 随源码一起提交。部署完成后再将平台实际提供的 streamlit.app 网址发给老师。

网页会自动建立 alice、shop_a、shop_b 三个虚拟账户，密码均为 DemoCash2026!。默认余额分别为100、0、0。每位访客的银行、钱包、商户数据分别存入随机会话目录，其他会话不共用实验余额；同一会话切换角色仍操作同一组数据。重新建立浏览器会话或服务重启后可能重置。服务器本地文件不作为持久备份，也不是操作系统级隔离。仅使用虚拟实验信息。

在线模式用 python -m streamlit run cloud_app.py。公开部署副本的 app.py 在未设置 ECASH_DATA 时同样默认使用访客隔离模式，兼容已选择 app.py 的部署。本地持久运行使用 start.command，或设置 ECASH_DATA=data 后运行 app.py；此时数据保存在指定目录。cloud_app.py 始终强制在线模式。

验证命令：

```sh
python -m unittest discover -s tests -v
python tests/ui_flow.py
python tests/cloud_flow.py
```

GitHub Pages 无法运行该Python应用。将源码放入GitHub仅完成代码托管，还需要网页运行平台。需要平台授权或同意服务条款时由账号本人确认。
