"""The new-trip button must honor the visible Deep Personalisation lock."""
import subprocess
from pathlib import Path


def test_new_trip_redirects_until_deep_personalisation_is_complete():
    program = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('static/app.js','utf8');
const handler=source.slice(source.indexOf('function toggleTripFormModal()'),source.indexOf('// Option A vs Option B Hotel Selection'));
const events=[],fields=new Map();
for(const id of ['tripEditOptions','tripDestSelect','tripStartDateInput','tripEndDateInput','tripHasChildrenCheck','tripHasElderlyCheck'])
 fields.set(id,{value:'',classList:{add(){}},disabled:false});
const context={console,Date,Map,Set,JSON,Number,String,Object,
 state:{currentUser:null,profileStatus:null},editingTripId:'unchanged',
 document:{getElementById:id=>fields.get(id)||null,querySelector:()=>null,querySelectorAll:()=>[]},
 closeModal:id=>events.push('close:'+id),openModal:id=>events.push('open:'+id),
 openPersonalProfileModal:()=>events.push('deep'),
 updateTripDurationPreview(){},syncTripPartyFromChecks:()=>events.push('prefill'),
 calculateTripMinimumBudget:()=>events.push('budget'),
 addEventListener(){},fetch:async()=>({ok:true,json:async()=>({profile_complete:true})})};
context.window=context;
vm.createContext(context);vm.runInContext(handler,context);
for(const status of [null,{complete:false}]) {
 context.state.profileStatus=status;events.length=0;context.toggleTripFormModal();
 assert.deepStrictEqual(events,['close:tripFormModal','deep']);
 assert.strictEqual(context.editingTripId,'unchanged','locked clicks must not reset trip editing');
 assert.strictEqual(fields.get('tripStartDateInput').value,'','locked clicks must not prefill the planner');
}
// The history gate wraps the button in production. A completed basic profile
// must still redirect to Deep Personalisation rather than bypass its lock.
vm.runInContext(fs.readFileSync('static/modules/profile.js','utf8'),context);
(async()=>{
 context.state.profileStatus={complete:false};events.length=0;
 context.toggleTripFormModal();await new Promise(resolve=>setImmediate(resolve));
 assert.deepStrictEqual(events,['close:tripFormModal','deep']);
 context.state.profileStatus={complete:true};events.length=0;
 context.toggleTripFormModal();await new Promise(resolve=>setImmediate(resolve));
 assert.deepStrictEqual(events,['prefill','open:tripFormModal','budget']);
 assert.strictEqual(context.editingTripId,null);
 console.log('Plan New Trip follows the Deep Personalisation lock: OK');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result=subprocess.run(['node','-e',program],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
