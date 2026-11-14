"""Prompt 5 regressions; intentionally unexecuted until the integration merge."""
import json
from pathlib import Path
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]


def javascript(expression):
    script=r"""
const vm=require('node:vm'),fs=require('node:fs');
const context={window:{},state:{currentUser:{user_id:'owner'}},AbortController,setTimeout,clearTimeout,URL,Intl,Date,console};
context.getWorkspaceContext=()=>({tripId:'trip'});vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
context.A=context.window.ExperienceAPI;
Promise.resolve(vm.runInContext(process.argv[2],context)).then(value=>process.stdout.write(JSON.stringify(value))).catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
"""
    result=subprocess.run(['node','-e',script,str(ROOT/'static/modules/experience_api.js'),expression],capture_output=True,text=True,check=True,cwd=ROOT)
    return json.loads(result.stdout)


@pytest.mark.parametrize('value',['',None,True,False,[],{},'   ','1.5','-1','Infinity'])
def test_whole_rupee_validation_rejects_invalid_input(value):
    assert javascript(f'A.integer({json.dumps(value)},0)') is False


@pytest.mark.parametrize('value',[0,1,'25000',1000000000])
def test_whole_rupee_validation_accepts_boundaries(value):
    assert javascript(f'A.integer({json.dumps(value)},0)') is True


def discovery(**overrides):
    return dict(origin='Pune',date_mode='dates',start_date='2099-01-01',end_date='2099-01-03',total_budget=30000,
                trip_type='family',adults=2,children=0,seniors=0,mood='culture',max_travel_hours='',walking_limit_km='',accessibility='',**overrides)


@pytest.mark.parametrize('field,value',[
    ('origin','  '),('origin','12345'),('total_budget',25000.5),('trip_type','unknown'),('children',True),
    ('adults',31),('mood','teleport'),('walking_limit_km',-1),('max_travel_hours','abc'),('accessibility','x'*501),
])
def test_discovery_errors_identify_the_field(field,value):
    values=discovery();values[field]=value
    assert field in javascript('A.discoveryErrors('+json.dumps(values)+',"2026-11-14")')


def test_adult_only_family_and_flexible_dates():
    assert javascript('A.discoveryErrors('+json.dumps(discovery())+',"2026-11-14")')=={}
    values=discovery();values.update(date_mode='flexible',duration_days=3);values.pop('start_date');values.pop('end_date')
    assert javascript('A.discoveryErrors('+json.dumps(values)+',"2026-11-14")')=={}


def test_past_dates_and_reversed_dates_rejected():
    values=discovery();values.update(start_date='2020-01-02',end_date='2020-01-01')
    errors=javascript('A.discoveryErrors('+json.dumps(values)+',"2026-11-14")')
    assert 'start_date' in errors and 'end_date' in errors


def test_unknown_amounts_stay_unknown_and_zero_is_distinct():
    result=javascript("[null,undefined,'',false,'   ',0].map(A.amount)")
    assert result==[None,None,None,None,None,0]


def test_financial_summary_uses_server_forecast_without_reconstructing_it():
    result=javascript("A.normalizeSummary({total_budget_inr:30000,actual_spending_inr:12000,estimated_remaining_costs_inr:15000,forecast_final_cost_inr:27000,available_buffer_inr:3000})")
    assert result['forecast_final_cost']==27000
    assert result['available_buffer']==3000
    assert javascript("A.normalizeSummary({total_budget_inr:30000,actual_spending_inr:12000}).available_buffer") is None


@pytest.mark.parametrize('field,value',[('amount_inr',0),('amount_inr',1.5),('category','credit_card'),('spent_on','2026-02-30'),('paid_by','x'*101)])
def test_expense_validation(field,value):
    record={'amount_inr':650,'category':'food','spent_on':'2026-11-14','description':'','paid_by':''};record[field]=value
    assert field in javascript('A.expenseErrors('+json.dumps(record)+')')


def test_features_fail_closed_without_server_capabilities():
    result=javascript("A.budgetOptions('trip',{current_budget_inr:20000,max_extra_inr:5000}).catch(e=>e.message)")
    assert 'unavailable' in result


def test_capabilities_are_not_reused_for_a_different_account():
    expression="fetch=async()=>({ok:true,status:200,json:async()=>({expense_tracking:true})});A.capabilities().then(()=>{state.currentUser={user_id:'someone-else'};return A.can('expense_tracking')})"
    assert javascript(expression) is False


def test_late_response_for_previous_account_is_not_displayed():
    expression="fetch=async()=>{state.currentUser={user_id:'someone-else'};return {ok:true,status:200,json:async()=>({private:'old-account'})}};A.request('/api/anything').catch(e=>e.message)"
    assert 'account changed' in javascript(expression)


def test_expense_idempotency_key_and_linked_payment_contract():
    expression="""let calls=[];fetch=async(url,options)=>{calls.push({url,method:options.method,body:options.body?JSON.parse(options.body):null,headers:options.headers});return {ok:true,status:200,json:async()=>url.includes('capabilities')?{expense_tracking:true}:{saved:true}}};
A.capabilities().then(()=>A.saveExpense('trip',{amount_inr:3000,category:'accommodation',planned_item_id:'stay-1',payment_state:'partial'},'expense-key')).then(()=>calls.at(-1))"""
    result=javascript(expression)
    assert result['headers']['Idempotency-Key']=='expense-key'
    assert result['body']['idempotency_key']=='expense-key'
    assert result['body']['payment_state']=='partial'
    assert result['body']['planned_item_id']=='stay-1'


def test_comparison_rejects_four_destinations_without_a_request():
    expression="fetch=async()=>({ok:true,status:200,json:async()=>({discovery:true})});A.capabilities().then(()=>A.compare(['a','b','c','d'])).catch(e=>e.message)"
    assert 'two or three' in javascript(expression)


def test_network_error_retains_retry_guidance():
    assert 'entries are kept' in javascript("fetch=async()=>{throw new TypeError('private transport')};A.request('/api/example').catch(e=>e.message)")


def test_assistant_proposal_paths_ignore_model_supplied_urls():
    expression="""let calls=[];fetch=async(url,options)=>{calls.push(url);return {ok:true,status:200,json:async()=>({assistant_actions:true})}};
A.capabilities().then(()=>A.assistantPreview('id/with/slashes','trip')).then(()=>calls.at(-1))"""
    assert javascript(expression)=='/api/assistant/proposals/id%2Fwith%2Fslashes/preview'


def test_main_menu_does_not_keep_a_previous_trip_as_assistant_context():
    assert javascript("location={hash:'#/'};A.workspaceTrip()") is None
    assert javascript("location={hash:'#/trips/new'};A.workspaceTrip()") is None
    assert javascript("location={hash:'#/trips/trip'};A.workspaceTrip()")=='trip'
    assert javascript("location={hash:'#/trips/%broken'};A.workspaceTrip()") is None


def test_travel_policies_are_not_mistaken_for_implementation_details():
    assert javascript("A.text('Check the hotel cancellation policy.')")=='Check the hotel cancellation policy.'
