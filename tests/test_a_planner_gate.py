"""Basic profile/history unlocks trip setup; deep profile gates itinerary generation."""
import subprocess
from pathlib import Path


def test_new_trip_opens_after_basic_profile_even_before_deep_personalisation():
    program = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('static/app.js','utf8');
const handler=source.slice(source.indexOf('function toggleTripFormModal()'),source.indexOf('// Option A vs Option B Hotel Selection'));
const events=[],fields=new Map();
const fakeElement=()=>({value:'',checked:false,disabled:false,classList:{add(){},remove(){},toggle(){}},dataset:{},setAttribute(){},removeAttribute(){},focus(){}});
const context={console,Date,Map,Set,JSON,Number,String,Object,
 state:{currentUser:{user_id:'user-1'},currentProfile:{residence_country:'IN',companions:'solo'},profileStatus:{complete:false},precision:{context:{},answers:{}}},editingTripId:'old-trip',
 document:{getElementById:id=>fields.get(id)||fakeElement(),querySelector:()=>null,querySelectorAll:()=>[]},
 closeModal:id=>events.push('close:'+id),openModal:id=>events.push('open:'+id),
 openPersonalProfileModal:()=>events.push('deep'),
 updateTripDurationPreview(){},syncTripPartyFromChecks:()=>events.push('prefill'),
 calculateTripMinimumBudget:()=>events.push('budget'),addEventListener(){},
 fetch:async()=>({ok:true,json:async()=>({profile_complete:true})})};
context.window=context;
vm.createContext(context);vm.runInContext(handler,context);
vm.runInContext(fs.readFileSync('static/modules/profile.js','utf8'),context);
(async()=>{
 context.toggleTripFormModal();
 await new Promise(resolve=>setImmediate(resolve));
 assert.deepStrictEqual(events,['prefill','open:tripFormModal','budget']);
 assert.strictEqual(context.editingTripId,null);
 const tripPlan=fs.readFileSync('app/modules/plan.py','utf8');
 assert.ok(tripPlan.includes('has_completed_deep_profile'), 'day-by-day itinerary generation remains protected by deep personalization');
 console.log('Basic profile unlocks trip setup; deep profile gates the itinerary: OK');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run(['node', '-e', program], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
