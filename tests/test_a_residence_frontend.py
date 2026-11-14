"""Prepared country/currency UI regressions. Do not run until push is requested."""
import subprocess
from pathlib import Path


def test_country_state_city_branching_and_currency_display():
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const nodes=new Map();
for(const id of ['residenceCountry','residenceState','residenceCity','preferredCurrency','residenceCityField',
 'residenceIndiaFields','residenceCurrencyFields','residenceRetry','displayCurrencyNotice','tripBudgetInput','tripBudgetCurrencyPreview',
 ...['residenceCountry','residenceState','residenceCity','preferredCurrency'].map(id=>id+'Error')]) {
 const classes=new Set();
 nodes.set(id,{value:'',options:[],dataset:{},events:{},textContent:'',
  classList:{toggle(name,hidden){if(hidden)classes.add(name);else classes.delete(name);},add(name){classes.add(name);},remove(name){classes.delete(name);},contains(name){return classes.has(name);}},
  replaceChildren(...values){this.options=values;},add(value){this.options.push(value);},
  addEventListener(name,fn){this.events[name]=fn;},focus(){}});
}
nodes.get('tripBudgetInput').value='25000';
const metadata={countries:[{code:'IN',name:'India',currencies:['INR']},{code:'US',name:'United States',currencies:['USD']}],
 currencies:['INR','USD','EUR'],indian_states:['Rajasthan','Tamil Nadu']};
const context={console,JSON,Number,String,Object,Map,Set,Intl,AbortController,setTimeout,clearTimeout,encodeURIComponent,
 Option:class{constructor(label,value){this.label=label;this.value=value;}},
 state:{basicAnswers:{},currentUser:{user_id:'account'}},document:{getElementById:id=>nodes.get(id)||null},
 fetch:async url=>({ok:true,json:async()=>url.includes('/config/residence')?metadata:
  url.includes('USD')?{available:true,currency:'USD',rate:0.012,as_of:'2026-11-14',stale:false}:
  {available:false,message:'Currency conversion is unavailable. Prices are shown in INR.'}})};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('static/modules/residence.js','utf8'),context);
(async()=>{
 const R=context.ResidenceForm;
 await R.render({});
 assert(nodes.get('residenceIndiaFields').classList.contains('hidden'));
 nodes.get('residenceCountry').value='IN';nodes.get('residenceCountry').events.change();
 assert(!nodes.get('residenceIndiaFields').classList.contains('hidden'));
 assert(nodes.get('residenceCityField').classList.contains('hidden'));
 assert.strictEqual(R.read(),null);
 assert(nodes.get('residenceStateError').textContent.includes('state'));
 nodes.get('residenceState').value='Rajasthan';nodes.get('residenceState').events.change();
 assert(!nodes.get('residenceCityField').classList.contains('hidden'));
 nodes.get('residenceCity').value='Jaipur';
 assert.strictEqual(R.read().preferred_currency,'INR');
 nodes.get('residenceCountry').value='US';nodes.get('residenceCountry').events.change();
 assert(nodes.get('residenceIndiaFields').classList.contains('hidden'));
 assert(nodes.get('residenceCity').disabled);
 assert.strictEqual(nodes.get('residenceCity').value,'');
 assert.strictEqual(R.read().residence_state,null);
 assert.strictEqual(R.read().preferred_currency,'USD');
 await context.UserCurrency.setProfile({residence_country:'US',preferred_currency:'USD'});
 const displayed=context.UserCurrency.formatAmount(25000,'₹25,000');
 assert(displayed.includes('₹25,000') && displayed.includes('300'));
 assert.strictEqual(nodes.get('tripBudgetInput').value,'25000','conversion must never change the INR budget');
 assert(nodes.get('tripBudgetCurrencyPreview').textContent.includes('INR above'));
 await context.UserCurrency.setProfile({residence_country:'US',preferred_currency:'EUR'});
 assert.strictEqual(context.UserCurrency.formatAmount(25000,'₹25,000'),'₹25,000');
 assert(nodes.get('displayCurrencyNotice').textContent.includes('unavailable'));
 console.log('Country branching, home-address reset, and currency fallback: OK');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
