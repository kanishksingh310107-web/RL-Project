/* E: shared safe rendering, inline validation and confirmation primitives. */
(() => {
  'use strict';
  const A=window.ExperienceAPI;
  const el=(tag,text,className)=>{const n=document.createElement(tag);if(text!==undefined&&text!==null)n.textContent=String(text);if(className)n.className=className;return n;};
  function button(label,work,style='ex-button'){const n=el('button',label,style);n.type='button';if(work)n.addEventListener('click',work);return n;}
  function status(parent){const n=el('p','','ex-status');n.setAttribute('role','status');n.setAttribute('aria-live','polite');parent.append(n);return n;}
  function field(form,name,label,{type='text',value='',options,min,max,required=false,help='',maxlength=200}={}) {
    const wrap=el('label',null,'ex-field'),title=el('span',label);wrap.append(title);
    const input=el(options?'select':type==='textarea'?'textarea':'input');input.name=name;input.id=`ex-${form.dataset.formId}-${name}`;
    if(options)for(const [v,t] of options){const option=el('option',t);option.value=v;input.append(option);}
    else if(type!=='textarea')input.type=type;
    if(min!==undefined)input.min=String(min);if(max!==undefined)input.max=String(max);if(type==='number')input.step='1';
    input.value=value??'';input.required=required;input.maxLength=maxlength;
    const error=el('span','','ex-error');error.id=input.id+'-error';error.dataset.errorFor=name;error.setAttribute('role','alert');input.setAttribute('aria-describedby',error.id);wrap.append(input);
    if(help)wrap.append(el('small',help));wrap.append(error);form.append(wrap);return input;
  }
  function errors(form,values={}) {
    form.querySelectorAll('[data-error-for]').forEach(n=>{n.textContent=values[n.dataset.errorFor]||'';const input=form.elements[n.dataset.errorFor];if(input)input.setAttribute('aria-invalid',String(!!values[n.dataset.errorFor]));});
    const first=Object.keys(values)[0];if(first)form.elements[first]?.focus();return !first;
  }
  function values(form){return Object.fromEntries(new FormData(form));}
  function form(id){const n=el('form',null,'ex-form');n.dataset.formId=id;n.noValidate=true;n.addEventListener('submit',event=>event.preventDefault());return n;}
  function dialog(title,description='') {
    const previous=document.activeElement,box=el('dialog',null,'ex-dialog');
    const heading=el('h2',title);heading.id='ex-dialog-'+A.nonce();box.setAttribute('aria-labelledby',heading.id);box.append(heading);
    if(description)box.append(el('p',description,'ex-muted'));
    const content=el('div'),notice=status(box),actions=el('div',null,'ex-actions');
    const mayClose=()=>{
      if(box.classList.contains('ex-chat'))return true;
      if(box.querySelector('form[data-inflight="true"]')){notice.textContent='Please wait for the request to finish.';return false;}
      return !box.querySelector('form[data-dirty="true"]')||window.confirm('Discard these unsaved form changes?');
    };
    const close=button('Close',()=>{if(mayClose())box.close();});actions.append(close);box.append(content,actions);document.body.append(box);
    box.addEventListener('cancel',event=>{if(!mayClose())event.preventDefault();});
    box.addEventListener('input',event=>{const form=event.target.closest('form');if(form&&!box.classList.contains('ex-chat'))form.dataset.dirty='true';});
    box.addEventListener('close',()=>{box.remove();if(previous?.isConnected)previous.focus();});box.showModal();
    return {box,content,notice,actions,close};
  }
  async function busy(control,notice,work) {
    if(control.disabled)return;control.disabled=true;control.setAttribute('aria-busy','true');notice.textContent='';notice.classList.remove('ex-error');
    const form=control.closest('form');const fields=form?[...form.querySelectorAll('input,select,textarea,button')].filter(n=>n!==control).map(n=>[n,n.disabled]):[];
    if(form)form.dataset.inflight='true';fields.forEach(([node])=>node.disabled=true);
    try{return await work();}catch(error){if(form&&error.field){const name=form.elements[error.field]?error.field:error.field.split('.').pop();if(form.elements[name])errors(form,{[name]:error.message});}notice.textContent=error.message;notice.classList.add('ex-error');return undefined;}finally{fields.forEach(([node,disabled])=>{if(node.isConnected)node.disabled=disabled;});if(form)form.dataset.inflight='false';if(control.isConnected){control.disabled=false;control.removeAttribute('aria-busy');}}
  }
  function unavailable(parent,message,work) {
    const box=el('div',null,'ex-unavailable');box.append(el('p',message));if(work)box.append(button('Retry availability',work));parent.append(box);return box;
  }
  function lines(parent,heading,items){const entries=(Array.isArray(items)?items:typeof items==='string'?[items]:[]).filter(item=>item!==null&&item!==undefined);if(!entries.length)return;parent.append(el('h4',heading));const list=el('ul');for(const item of entries)list.append(el('li',A.text(typeof item==='string'?item:item.message||item.title||item.name||'')));parent.append(list);}
  function safeLinks(parent,sources=[]) {
    for(const source of Array.isArray(sources)?sources:[]){try{const url=new URL(source.url);if(!['https:','http:'].includes(url.protocol))continue;const a=el('a',source.title||source.label||url.hostname);a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';parent.append(a);}catch(_){}}
  }
  function confirmation(title,proposal,{current,confirm,done}={}) {
    if(!proposal||typeof proposal.token!=='string'||!proposal.token)throw new Error('The server did not return a valid preview. No changes were applied.');
    const d=dialog(title,'Review this server-generated proposal. Nothing changes until you confirm.');
    d.close.textContent='Cancel';d.content.append(el('p',A.text(proposal.summary||proposal.title||'Proposed change')));
    if(proposal.time_impact)d.content.append(el('p','Timing: '+A.text(proposal.time_impact)));
    if(proposal.budget_impact)d.content.append(el('p','Budget: '+A.text(proposal.budget_impact)));
    if(A.amount(proposal.cost_delta_inr)!==null)d.content.append(el('p','Estimated cost change: '+A.money(proposal.cost_delta_inr)));
    lines(d.content,'Warnings',proposal.warnings);lines(d.content,'What changes',proposal.changes);
    if(Array.isArray(proposal.timeline)){const list=el('ol');for(const block of proposal.timeline)list.append(el('li',`${block.day_number?'Day '+block.day_number+' · ':''}${block.time_range||'Time unavailable'} · ${block.title||''}`));d.content.append(list);}
    const apply=button('Confirm change',()=>busy(apply,d.notice,async()=>{if(current&&!current())throw new Error('The trip or account changed. Request a fresh preview.');d.close.disabled=true;try{const result=await confirm(proposal.token);d.box.close();await done?.(result);}finally{if(d.close.isConnected)d.close.disabled=false;}}),'ex-primary');
    d.actions.prepend(apply);d.box.addEventListener('cancel',event=>{if(apply.disabled)event.preventDefault();});return d;
  }
  const today=()=>window.TripExperience?.indiaToday()||new Date().toISOString().slice(0,10);
  const validContext=key=>key===A.contextKey();
  async function planningGate(){return !!(await window.ProfileGate?.require())&&!!window.TripExperience?.allowPlanning();}
  window.ExperienceUI={el,button,status,field,errors,values,form,dialog,busy,unavailable,lines,safeLinks,confirmation,today,validContext,planningGate};
  window.addEventListener('trip:context-cleared',()=>document.querySelectorAll('dialog.ex-dialog[open]').forEach(box=>box.close()));
})();
