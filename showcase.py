"""A full-screen visual layer hosted by the existing Streamlit application."""
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent


def scene_configuration(initial=0, base_path=''):
    manifest = json.loads((ROOT/'static/scenes/manifest.json').read_text())
    specs = [
        ('home','首页','课程作业','作业实时更新','《密码货币与区块链技术》杨雅评课程作业','./bank','进入银行工作台',
         [{'goto':1,'label':'进入线上银行','x':4,'y':79,'w':29,'h':14},
          {'goto':2,'label':'查看节点模拟器','x':34,'y':79,'w':31,'h':14},
          {'goto':3,'label':'查看课程作业','x':66,'y':79,'w':30,'h':14},
          {'goto':1,'label':'开始探索','x':4,'y':50,'w':12,'h':6}]),
        ('bank','线上银行','线上银行','OFFLINE CASH / TEACHING BANK','盲签发行 · 离线支付 · 双花追踪','./bank','进入银行工作台',
         [{'label':'进入银行工作台管理账户','x':3,'y':42,'w':92,'h':51}]),
        ('nodes','节点模拟器','节点模拟器','P2P / NETWORK SIMULATION','连接100个节点，看见区块如何同步。','./p2p','打开节点模拟器',
         [{'label':'运行节点模拟实验','x':4,'y':30,'w':12,'h':6}]),
        ('coursework','课程作业','课程作业','COURSEWORK / ASSIGNMENTS','教师题目与我的回答','./coursework','查看课程题目与答案',
         [{'label':'查看课程题目与我的答案','x':4,'y':43,'w':92,'h':51}]),
    ]
    scenes=[]
    for key,title,heading,eyebrow,description,href,action,hotspots in specs:
        meta=manifest[key]
        scenes.append(dict(id=key,title=title,heading=heading,eyebrow=eyebrow,description=description,
                           href=href,action=action,hotspots=hotspots,file=meta['file'],width=meta['width'],height=meta['height'],
                           alt=f'{title}，已确认的青绿色玻璃风格页面设计。'+description))
    return {'initial':initial,'assetRoot':'/'+base_path.strip('/')+'/'+'app/static/scenes/' if base_path else '/app/static/scenes/',
            'scenes':scenes}


@st.cache_data(show_spinner=False)
def render_showcase(initial=0, base_path='', version='1'):
    folder=ROOT/'web/showcase'
    html=(folder/'index.html').read_text()
    replacements={'__STYLES__':(folder/'styles.css').read_text(),
                  '__CONFIG__':json.dumps(scene_configuration(initial,base_path),ensure_ascii=False).replace('</',r'<\/'),
                  '__MOTION_CORE__':(folder/'motion-core.js').read_text(),
                  '__CONTROLLER__':(folder/'controller.js').read_text()}
    for token,value in replacements.items():
        html=html.replace(token,value)
    return html


def main():
    from interactive import main as run_live
    run_live()


if __name__ == '__main__':
    main()
