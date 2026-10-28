"""Numbered teacher questions on the left, the student's answer on the right."""
import json
from pathlib import Path

import streamlit as st

ROOT=Path(__file__).resolve().parent


def load_questions(path=ROOT/'content/coursework.json'):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data,list) or len(data)>1000:
        raise ValueError('题目清单格式不正确')
    seen=set()
    for q in data:
        if not isinstance(q,dict) or not isinstance(q.get('id'),int) or isinstance(q.get('id'),bool) or not 1<=q['id']<=999:
            raise ValueError('题目编号必须在001至999之间')
        if q['id'] in seen or not isinstance(q.get('question'),str) or not q['question'].strip() or len(q['question'])>20000:
            raise ValueError('题目内容或编号不正确')
        if not isinstance(q.get('answer',''),str) or len(q.get('answer',''))>100000:
            raise ValueError('答案内容不正确')
        seen.add(q['id'])
    return sorted(data,key=lambda q:q['id'])


def main():
    st.markdown('''<style>
.stApp{background:#020708;color:#f1f7f7}.block-container{max-width:1250px}
h1,h2,h3{color:#f3f7f7}.stTextArea textarea{background:#071315;color:#edf6f6}
[data-testid="stSidebar"]{background:#051012}[data-testid="stSidebar"] *{color:#d5ecec}
</style>''',unsafe_allow_html=True)
    st.caption('COURSEWORK / ASSIGNMENTS')
    st.title('课程作业')
    st.write('教师题目与我的回答')
    try:
        questions=load_questions()
    except (ValueError,OSError) as exc:
        st.error(f'题目暂时无法读取：{exc}')
        return
    left,right=st.columns([1,2.3],gap='large')
    with left:
        st.subheader('题目导航')
        search=st.text_input('搜索题目',placeholder='输入题目关键词')
        visible=[q for q in questions if search.casefold() in (q['question']+f'{q["id"]:03d}').casefold()]
        if not visible:
            st.caption('暂无题目' if not questions else '没有匹配的题目')
        else:
            chosen=st.radio('选择题目',[q['id'] for q in visible],format_func=lambda i:f'问题{i:03d}',label_visibility='collapsed')
    with right:
        if not questions:
            st.info('暂未录入老师布置的题目。收到题目后，会按问题001、002、003…展示。')
            return
        if not visible:
            st.info('请调整关键词查看题目。')
            return
        question=next(q for q in visible if q['id']==chosen)
        st.caption(f'问题{chosen:03d}')
        st.subheader('题目')
        st.write(question['question'])
        st.divider()
        st.subheader('我的答案')
        saved_key=f'course_answer_{chosen}'
        with st.form(f'answer_{chosen}'):
            answer=st.text_area('答案',value=st.session_state.get(saved_key,question.get('answer','')),height=280,
                                placeholder='在此填写你的答案…',label_visibility='collapsed',max_chars=100000)
            if st.form_submit_button('保存答案',type='primary'):
                st.session_state[saved_key]=answer
                st.success('已保存在本次会话中，可下载留存。')
        exported={'id':chosen,'question':question['question'],'answer':st.session_state.get(saved_key,question.get('answer',''))}
        st.download_button('下载我的答案',json.dumps(exported,ensure_ascii=False,indent=2),f'问题{chosen:03d}.json','application/json')
        st.caption('会话中的编辑请下载留存。页面只展示老师的题目与个人作答，不设分类或状态标签。')


if __name__=='__main__':
    main()
