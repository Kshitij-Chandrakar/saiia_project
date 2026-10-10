import asyncio
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.grpc_utterance_buffer import UtteranceBuffer, topic_question, merge
from app.grpc_answer_pipeline import detect_intake_question

@pytest.mark.parametrize('text',['supervised learning','database indexing','REST API','pointers in C','normalization in DBMS','machine learning vs deep learning'])
def test_technical_topic_prompts(text):
    candidate,reason=asyncio.run(detect_intake_question(text,allow_topics=True))
    assert candidate.lower().startswith('explain ')
    assert reason=='topic_prompt_accepted'
    assert asyncio.run(detect_intake_question(text))[1]=='not_question'

@pytest.mark.parametrize('text',['yes','okay','hello','hmm','SQL SQL','machine learning machine learning','click REST API','purple SQL banana'])
def test_noise_is_not_a_topic(text):
    assert topic_question(text) is None
    assert asyncio.run(detect_intake_question(text,allow_topics=True))[1] in ('too_short','not_question')

@pytest.mark.parametrize('left,right,expected',[
 ('what is','supervised learning','What is supervised learning?'),
 ('explain','SQL','Explain SQL.'),
 ('difference between','machine learning and deep learning','Difference between machine learning and deep learning?'),
])
def test_adjacent_final_completion(left,right,expected):
    now=[10.0];buffer=UtteranceBuffer(clock=lambda:now[0])
    first,_=buffer.assemble(left,0);buffer.hold(first)
    now[0]+=.4
    combined,merged=buffer.assemble(right,1)
    assert merged and combined==expected
    assert not asyncio.run(detect_intake_question(combined,allow_topics=True))[1]

def test_partial_completion_expiry_and_bounded_memory():
    now=[10.0];buffer=UtteranceBuffer(clock=lambda:now[0])
    buffer.partial_update('what is',0)
    assert buffer.assemble('supervised learning',1)==('What is supervised learning?',True)
    buffer.hold('difference between');now[0]+=5
    assert buffer.assemble('database indexing',2)==('database indexing',False)
    for i in range(20): buffer.partial_update('x'*10000,i)
    assert len(buffer.recent)==8 and len(buffer.partial)==4096
    assert len(buffer.snapshot()['utterance_buffer_text'])==256
    assert merge('supervised learning','supervised learning')=='supervised learning'


def test_incomplete_prefix_cannot_turn_filler_into_a_question():
    buffer=UtteranceBuffer()
    buffer.hold('what is')
    text,merged=buffer.assemble('yes',1)
    assert text=='yes' and not merged
    assert asyncio.run(detect_intake_question(text,allow_topics=True))[1]=='too_short'
