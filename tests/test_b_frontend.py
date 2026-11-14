"""Exercise the account, scheduling and live fetch wrappers together."""
import subprocess
from pathlib import Path


def test_schedule_wrapper_preserves_live_payloads_and_session():
    program = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const values={hotelArrivalTime:'14:00',hotelDepartureTime:'11:00',wakeTime:'07:00',activityStartTime:'09:00',bedTime:'21:00',tripStartDateInput:'2027-03-01',tripEndDateInput:'2027-03-03'};
const elements=new Map(),requests=[];
for(const id of ['schedulePrefsMount','freeBlocksList','freeBlocksError','addFreeBlockBtn','tripCreateForm',...Object.keys(values),...Object.keys(values).map(id=>id+'Error')])
  elements.set(id,{value:values[id]||'',children:[],textContent:'',events:{},addEventListener(name,fn){this.events[name]=fn;}});
const context={console,URL,Headers,Request,Map,Set,Number,String,JSON,Object,Error,encodeURIComponent,
  location:{href:'http://localhost/'},localStorage:{getItem:()=>JSON.stringify({token:'signed-in-token'})},
  document:{getElementById:id=>elements.get(id)||null,querySelectorAll:()=>[],querySelector:()=>null,addEventListener(){}},
  addEventListener(){},fetch:async(url,init)=>{requests.push({url,init});return {ok:true,json:async()=>({})};}};
context.window=context;
vm.createContext(context);
for(const file of ['auth','schedule_prefs','live_trip','post_trip'])vm.runInContext(fs.readFileSync('static/modules/'+file+'.js','utf8'),context);
(async()=>{
 const C=context.CTripRuntime,ctx={tripId:'trip',userId:'user'};
 for(const path of ['/finalize','/start','/activities/place/review','/post-feedback']) {
   const body=path.endsWith('review')?{action:'keep',ratings:{overall:4}}:{};
   await C.api(ctx,path,body);
   const request=requests.at(-1);
   assert.deepStrictEqual(JSON.parse(request.init.body),body,'schedule preferences must not tamper with live requests');
   assert.strictEqual(new Headers(request.init.headers).get('Authorization'),'Bearer signed-in-token');
 }
 await context.fetch('/api/trips/user',{method:'POST',body:JSON.stringify({destination_id:'jaipur_india'})});
 assert.strictEqual(JSON.parse(requests.at(-1).init.body).schedule_prefs.hotel_arrival_time,'14:00');
 elements.get('hotelDepartureTime').value='05:00';
 let prevented=false;
 elements.get('tripCreateForm').events.submit({preventDefault(){prevented=true;},stopImmediatePropagation(){}});
 assert(prevented,'departure with no final-day activity window must be blocked');
 assert(elements.get('hotelDepartureTimeError').textContent.includes('activity window'));
 assert.strictEqual(elements.get('hotelDepartureTime').value,'05:00','entered values survive validation');
 console.log('Integrated wrappers, session forwarding and departure validation: OK');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run(['node','-e',program],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
    assert result.returncode == 0, result.stdout + result.stderr
