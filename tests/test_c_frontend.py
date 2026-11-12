"""C frontend field validation, safe rendering and failure cleanup without a browser dependency."""
import subprocess
from pathlib import Path


def test_c_frontend_validation_errors_and_retry_cleanup():
    root=Path(__file__).resolve().parents[1]
    program=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const context={window:{addEventListener(){}},document:{},console,JSON,Number,String,Object,Error,
  encodeURIComponent,fetch:async()=>({ok:false,json:async()=>({detail:'Choose a valid rating',field:'ratings.overall',code:'INVALID_INPUT'})})};
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/modules/live_trip.js','utf8'),context);
vm.runInContext(fs.readFileSync('static/modules/post_trip.js','utf8'),context);
const C=context.window.CTripRuntime;
assert(context.window.CPostTrip.render);
assert.strictEqual(C.esc('<img src=x onerror=alert(1)>'),'&lt;img src=x onerror=alert(1)&gt;');
let field={value:'4',dataset:{rating:'overall'}},inline={textContent:''};
const form={querySelectorAll:()=>[field],querySelector:()=>inline};
assert.strictEqual(C.readRatings(form).overall,4);
for(const value of ['0','6','4.5','not-a-number','']) {
  field.value=value;assert.strictEqual(C.readRatings(form),null);assert(inline.textContent.includes('1 to 5'));
}
field.value='';assert.strictEqual(Object.keys(C.readRatings(form,false)).length,0);
const html=C.ratingFields(['overall'],{overall:5});assert(html.includes('required'));assert(html.includes('data-rating-error="overall"'));
(async()=>{
  const control={disabled:false,isConnected:true},message={innerHTML:''},box={querySelector:()=>message};
  await C.submitButton(control,box,async()=>{throw new Error('<script>network</script>');});
  assert.strictEqual(control.disabled,false);assert(message.innerHTML.includes('&lt;script&gt;'));assert(!message.innerHTML.includes('<script>'));
  let error;try{await C.api({tripId:'trip',userId:'user'},'/post-feedback',{});}catch(e){error=e;}
  assert.strictEqual(error.field,'ratings.overall');assert.strictEqual(error.code,'INVALID_INPUT');
  context.fetch=async()=>{throw new Error('private transport detail');};
  try {await C.api({tripId:'trip',userId:'user'},'/runtime',null,'GET');assert.fail('expected error');}
  catch(e) {assert(e.message.includes('entries')||e.message.includes('information'));assert(!e.message.includes('private'));}
  console.log('C frontend validation, escaping, API errors and retry cleanup: OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    result=subprocess.run(['node','-e',program],cwd=root,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
