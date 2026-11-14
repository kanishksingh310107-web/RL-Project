"""Google credential handling and the official-button frontend without real accounts."""
from pathlib import Path
import subprocess
from unittest.mock import Mock
import requests
from app.database import get_connection


def test_verified_google_token_returns_stable_account(client,monkeypatch):
    from app import auth
    client_id='123456789-example.apps.googleusercontent.com'
    monkeypatch.setenv('GOOGLE_CLIENT_ID',client_id)
    verifier=Mock(return_value={'sub':'verified-google-identity','email':'verified@example.com',
                               'email_verified':True,'name':'Verified traveller'})
    monkeypatch.setattr(auth.id_token,'verify_oauth2_token',verifier)
    first=client.post('/api/auth/google-token',json={'credential':'signed-google-credential-value'})
    second=client.post('/api/auth/google-token',json={'credential':'signed-google-credential-value'})
    assert first.status_code==second.status_code==200,first.text
    assert first.json()['user_id']==second.json()['user_id']
    assert first.json()['token'] and first.json()['has_profile'] is False
    assert verifier.call_args.args[2]==client_id
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE google_sub='verified-google-identity'").fetchone()[0]==1


def test_unverified_google_email_rejected(client,monkeypatch):
    from app import auth
    monkeypatch.setenv('GOOGLE_CLIENT_ID','123456789-example.apps.googleusercontent.com')
    monkeypatch.setattr(auth.id_token,'verify_oauth2_token',Mock(return_value={
        'sub':'unverified-identity','email':'unverified@example.com','email_verified':False}))
    response=client.post('/api/auth/google-token',json={'credential':'signed-google-credential-value'})
    assert response.status_code==401
    assert response.json()['code']=='GOOGLE_INVALID_CREDENTIAL'
    with get_connection() as conn:
        assert not conn.execute("SELECT 1 FROM users WHERE google_sub='unverified-identity'").fetchone()


def test_google_provider_failure_is_readable(client,monkeypatch):
    from app import auth
    monkeypatch.setenv('GOOGLE_CLIENT_ID','123456789-example.apps.googleusercontent.com')
    monkeypatch.setattr(auth.id_token,'verify_oauth2_token',Mock(side_effect=requests.ConnectionError('private transport details')))
    response=client.post('/api/auth/google-token',json={'credential':'signed-google-credential-value'})
    assert response.status_code==503 and response.json()['code']=='GOOGLE_UNAVAILABLE'
    assert 'private' not in response.text


def test_google_without_configuration_never_fakes_login(client,monkeypatch):
    from app import auth
    monkeypatch.setenv('GOOGLE_CLIENT_ID','')
    monkeypatch.setattr(auth,'GOOGLE_CLIENT_ID','')
    response=client.post('/api/auth/google-token',json={'credential':'signed-google-credential-value'})
    assert response.status_code==503 and response.json()['code']=='GOOGLE_NOT_CONFIGURED'


def test_google_button_initializes_once_and_saves_verified_session():
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const nodes=new Map();
for(const id of ['googleChooserBtn','googleAuthStatus','googleOfficialBtn','googleSetupLink','googleBtnLabel','googleOriginHint']){
 const classes=new Set();nodes.set(id,{textContent:'',disabled:false,childElementCount:0,clientWidth:320,
  classList:{toggle(name,on){if(on)classes.add(name);else classes.delete(name);},add(name){classes.add(name);}},
  replaceChildren(){this.childElementCount=0;},scrollIntoView(){}});
}
let initialization,initializations=0,configRequests=0,resets=0,view,stored;
const context={console,AbortController,setTimeout,clearTimeout,JSON,Object,Number,Math,
 state:{currentUser:null},location:{origin:'http://localhost:8000'},
 document:{readyState:'complete',getElementById:id=>nodes.get(id)||null},
 addEventListener(){},removeEventListener(){},
 google:{accounts:{id:{initialize(value){initialization=value;initializations++;},renderButton(node){node.childElementCount++;}}}},
 localStorage:{setItem(key,value){stored=JSON.parse(value);}},updateNavUser(){},resetAnswers(){resets++;},showView(value){view=value;},
 formatApiError(data,fallback){return data.detail||fallback;},
 fetch:async url=>({ok:true,json:async()=>{
  if(url.includes('/config/google')){configRequests++;return {client_id:'123456789-example.apps.googleusercontent.com',can_configure:true};}
  return {user_id:'verified-user',token:'session-token',has_profile:false};
 }})};context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('static/modules/google_login.js','utf8'),context);
(async()=>{
 await Promise.all([context.initGoogleGIS(),context.initGoogleGIS()]);
 assert.strictEqual(initializations,1);assert.strictEqual(configRequests,1);
 await initialization.callback({credential:'signed-google-credential-value'});
 assert.strictEqual(stored.token,'session-token');assert.strictEqual(context.state.currentUser.user_id,'verified-user');
 assert.strictEqual(view,'onboarding');assert.strictEqual(resets,1);
 assert.strictEqual(nodes.get('googleChooserBtn').disabled,false);
 console.log('Official Google button initialization and session handoff: OK');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
