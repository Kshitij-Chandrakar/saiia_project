import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace as NS
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app.api import onboarding
from app.auth.supabase_auth import get_current_user, CurrentUser
from app.cloud.onboarding import OnboardingService, OnboardingUnavailable

class Store:
    def __init__(self): self.step_value=1; self.completed=None; self.calls=[]
    def read(self, user):
        self.calls.append(user)
        return {'onboarding_current_step':self.step_value,'onboarding_completed_at':self.completed}
    def step(self,user,value):
        if not self.completed: self.step_value=value
        return self.read(user)
    def complete(self,user):
        self.completed=self.completed or 'saved-time'
        return self.read(user)

@pytest.fixture
def client():
    app=FastAPI(); app.include_router(onboarding.router,prefix='/api/onboarding')
    store=Store()
    app.dependency_overrides[onboarding.service]=lambda:store
    app.dependency_overrides[get_current_user]=lambda:CurrentUser(user_id='verified-owner')
    return TestClient(app),store,app

def test_navigation_refresh_and_completion_are_owned_and_idempotent(client):
    api,store,_=client
    assert api.get('/api/onboarding').json()['onboarding_current_step']==1
    assert api.patch('/api/onboarding/step',json={'current_step':4}).json()['onboarding_current_step']==4
    assert api.patch('/api/onboarding/step',json={'current_step':3}).json()['onboarding_current_step']==3
    assert api.get('/api/onboarding').json()['onboarding_current_step']==3
    assert api.post('/api/onboarding/complete').json()['onboarding_completed_at']=='saved-time'
    assert api.post('/api/onboarding/complete').json()['onboarding_completed_at']=='saved-time'
    assert api.patch('/api/onboarding/step',json={'current_step':2}).json()['onboarding_current_step']==3
    assert set(store.calls)=={'verified-owner'}

@pytest.mark.parametrize('payload',[{'current_step':0},{'current_step':6},{'current_step':True},{'current_step':2,'user_id':'other'}])
def test_invalid_or_browser_ownership_rejected(client,payload):
    api,_,_=client
    assert api.patch('/api/onboarding/step',json=payload).status_code==422

def test_unauthenticated_and_safe_failure(client):
    api,_,app=client
    def unavailable(user): raise OnboardingUnavailable('private internals')
    app.dependency_overrides[onboarding.service]=lambda:NS(read=unavailable)
    response=api.get('/api/onboarding')
    assert response.status_code==503 and 'private' not in response.text
    app.dependency_overrides.pop(get_current_user)
    assert api.get('/api/onboarding').status_code==401

def test_rest_filters_and_narrow_mutations_preserve_preferences():
    calls=[]
    row={'onboarding_current_step':3,'onboarding_completed_at':None,'preferred_answer_style':'balanced','preferred_answer_length':'standard'}
    class Transport:
        def request(self,method,url,**kwargs):
            calls.append((method,kwargs))
            return NS(status_code=200,json=lambda:[row])
    store=OnboardingService(Transport(),NS(supabase_url='https://synthetic.invalid',service_role_key='synthetic-private'))
    store.step('owner',4);store.complete('owner')
    assert calls[0][1]['json']=={'onboarding_current_step':4}
    assert set(calls[1][1]['json'])=={'onboarding_completed_at'}
    assert all(item[1]['params']['user_id']=='eq.owner' for item in calls)
    assert all(item[1]['params']['onboarding_completed_at']=='is.null' for item in calls)
    assert row['preferred_answer_style']=='balanced'

def test_completed_row_is_not_recompleted_or_rewound():
    calls=[]
    row={'onboarding_current_step':5,'onboarding_completed_at':'original-time','preferred_answer_length':'standard','preferred_answer_style':'balanced'}
    class Transport:
        def request(self,method,url,**kwargs):
            calls.append((method,kwargs))
            return NS(status_code=200,json=lambda:[] if method=='PATCH' else [row])
    store=OnboardingService(Transport(),NS(supabase_url='https://synthetic.invalid',service_role_key='synthetic-private'))
    assert store.complete('owner')['onboarding_completed_at']=='original-time'
    assert store.step('owner',1)['onboarding_current_step']==5
    assert [method for method,_ in calls]==['PATCH','GET','PATCH','GET']
