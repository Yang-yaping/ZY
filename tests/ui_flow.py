import os,tempfile,sys
from pathlib import Path
from streamlit.testing.v1 import AppTest
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from ecash.bank import Bank
with tempfile.TemporaryDirectory() as tmp:
 os.environ['ECASH_DATA']=tmp
 b=Bank(Path(tmp)/'bank.db'); b.initialize()
 for name,kind in [('alice','payer'),('shop_a','merchant'),('shop_b','merchant')]:b.create_account(name,'password123',kind)
 at=AppTest.from_file(str(root/'app.py'),default_timeout=30).run()
 def check():
  assert not at.exception, str(at.exception)
 def button(label):
  next(x for x in at.button if x.label==label).click().run();check()
 def page(name):
  at.sidebar.radio[0].set_value(name).run();check()
  if name in ('付款人','收款人') and at.text_input:
   at.text_input[0].set_value('password123').run();check()
 check(); print('overview OK')
 page('银行'); print('bank OK')
 page('付款人');at.text_input[0].set_value('password123').run();check()
 button('① 生成候选电子现金并盲化'); button('② 提交盲化值，接收银行随机抽查');button('③ 回应抽查 → 银行盲签 → 去盲');print('withdrawal UI OK')
 page('收款人');at.text_input[0].set_value('password123').run();check();button('① 验银行签名并产生独立随机挑战')
 page('付款人');button('④ 生成挑战响应')
 page('收款人');button('② 离线验证响应并验收');button('③ 提交银行存款');print('payment UI OK')
 assert b.account('shop_a','password123')['balance']==10
 page('收款人');at.selectbox(key='mname').set_value('shop_b').run();check()
 button('① 验银行签名并产生独立随机挑战')
 page('付款人');at.checkbox[0].check().run();button('④ 生成挑战响应')
 page('收款人');at.selectbox(key='mname').set_value('shop_b').run();check();button('② 离线验证响应并验收');button('③ 提交银行存款')
 assert b.account('shop_b','password123')['balance']==0
 assert len(b.dashboard()['evidence'])==1
 print('double-spend UI OK; second credit refused')
 page('场景与验收');print('scenarios OK')
print('PASS: five pages, withdrawal, offline challenge/response, deposit and balance')
