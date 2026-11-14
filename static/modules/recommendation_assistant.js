/* E: contextual chat and allowlisted, explicitly confirmed proposal cards. */
(() => {
  'use strict';
  const A=window.ExperienceAPI,U=window.ExperienceUI;
  if(!A||!U||typeof document==='undefined')return;
  const sessions=new Map();let drawer=null,account=A.uid();
  const actions=new Set(['swap_activity','remove_activity','reorder_activity','move_activity','add_activity','adjust_schedule','update_budget','apply_budget_option','record_expense','update_expense','apply_day_option']);
  function context() {
    const trip=A.workspaceTrip();
    return {trip,key:`${A.uid()||''}:${trip||'general'}`};
  }
  function session(key){if(!sessions.has(key))sessions.set(key,{messages:[],draft:'',conversationId:null,inFlight:false});return sessions.get(key);}
  function current(key){return !!drawer&&drawer.box.isConnected&&key===context().key;}
  const launcher=U.button('Ask your travel assistant',()=>open(),'ex-assistant-launcher');launcher.id='exAssistantLauncher';launcher.hidden=true;launcher.setAttribute('aria-haspopup','dialog');document.body.append(launcher);
  function visibility() {
    if(account!==A.uid()){sessions.clear();account=A.uid();drawer?.box.close();drawer=null;}
    const visible=!!A.uid()&&document.getElementById('authView')?.classList.contains('hidden')&&(!document.getElementById('dashboardView')?.classList.contains('hidden')||!document.getElementById('tripExperienceView')?.hidden);
    launcher.hidden=!visible;
    if(!visible&&drawer){drawer.box.close();drawer=null;}
  }
  for(const id of ['dashboardView','authView','tripExperienceView']){const node=document.getElementById(id);if(node)new MutationObserver(visibility).observe(node,{attributes:true,attributeFilter:['class','hidden']});}
  async function open() {
    if(!A.uid())return;
    if(drawer?.box.isConnected){drawer.box.focus();return;}
    drawer=U.dialog('Your recommendation assistant','Ask about your preferences, suggestions, itinerary or recorded budget.');drawer.box.classList.add('ex-chat');
    drawer.box.id='exAssistantDrawer';drawer.close.textContent='Close assistant';drawer.box.addEventListener('close',()=>{drawer=null;});
    await render();
  }
  async function render() {
    if(!drawer)return;
    const d=drawer,{trip,key}=context(),s=session(key);d.content.replaceChildren();d.notice.textContent='';
    const title=trip?'Selected trip: '+(typeof activeUserTrips!=='undefined'?activeUserTrips.find(t=>t.id===trip)?.destination_name||trip:trip):'General discovery — no trip selected';d.content.append(U.el('p',title,'ex-note'));
    const privacy=U.el('p','Checking assistant availability…','ex-muted');d.content.append(privacy);
    const transcript=U.el('div',null,'ex-chat-messages');transcript.setAttribute('role','log');transcript.setAttribute('aria-live','polite');transcript.setAttribute('aria-label','Assistant conversation');d.content.append(transcript);
    for(const record of s.messages)message(transcript,record,trip,key);
    const quick=U.el('div',null,'ex-actions');
    const composer=U.form('assistant');const input=U.field(composer,'message','Your message',{type:'textarea',value:s.draft,maxlength:2000,required:true,help:'Do not enter payment details, passwords or private booking credentials.'});
    input.rows=3;input.addEventListener('input',()=>{s.draft=input.value;});
    const send=U.el('button',s.inFlight?'Sending…':'Send message','ex-primary');send.type='submit';composer.append(send);
    for(const prompt of ['Why was this recommended?','Find somewhere quieter.','What could ₹5,000 more get me?','Show cheaper alternatives.','Help me choose a destination.',...(trip?["Explain today’s schedule.",'We are running late.','How much budget remains?']:[])]){const suggestion=U.button(prompt,()=>{input.value=prompt;s.draft=prompt;input.focus();});suggestion.disabled=s.inFlight;quick.append(suggestion);}
    d.content.append(quick,composer);
    const clear=U.button('Clear chat',()=>clearChat(s,key));d.content.append(clear);
    composer.onsubmit=event=>{event.preventDefault();if(s.inFlight)return;const value=input.value.trim();if(!U.errors(composer,!value?{message:'Enter a question.'}:value.length>2000?{message:'Use 2,000 characters or fewer.'}:{}))return;
      const failed=s.messages.findLast(r=>r.role==='user'&&r.status==='failed'&&r.text===value);
      const record=failed||{role:'user',text:value,status:'pending',key:A.nonce(),payload:{message:value,trip_id:trip,conversation_id:s.conversationId}};
      if(!failed)s.messages.push(record);s.draft=input.value;deliver(s,record,trip,key);
    };
    send.disabled=s.inFlight||!A.can('assistant_chat');input.disabled=s.inFlight;clear.disabled=s.inFlight;
    await A.capabilities();if(!current(key))return;
    if(A.can('assistant_chat')) {
      const caps=await A.capabilities();privacy.textContent=caps.conversation_persistence==='server'?'Conversations may be saved on the server. Use Clear chat to choose local clearing or request server deletion.':'Messages in this view are kept in memory for this session. Server retention is not confirmed; clearing the view alone does not delete server records.';
      if(!s.inFlight)send.disabled=false;
    } else {
      privacy.textContent='The assistant is currently unavailable. Destination discovery and ordinary planning controls remain available.';send.disabled=true;
      U.unavailable(d.content,'You do not need to configure anything to use the assistant.',async()=>{await A.capabilities(true);if(current(key))await render();});
    }
  }
  function message(parent,record,trip,key) {
    const card=U.el('article',null,'ex-chat-message ex-chat-'+record.role);card.append(U.el('strong',record.role==='user'?'You':'Travel assistant'),U.el('p',A.text(record.text),'ex-chat-text'));
    if(record.role==='user'&&record.status==='failed'){
      card.append(U.el('p',record.error||'This message was not confirmed. Retry sends the same request safely.','ex-error'));
      const retry=U.button('Retry this message',()=>deliver(session(key),record,trip,key));retry.disabled=session(key).inFlight;card.append(retry);
    }
    if(record.role==='user'&&record.status==='sending')card.append(U.el('small','Sending…'));
    if(record.role==='assistant') {
      if(record.uncertainty)card.append(U.el('p',A.text(record.uncertainty),'ex-note'));
      if(record.as_of)card.append(U.el('small','Information dated '+record.as_of));
      U.safeLinks(card,record.sources);
      for(const proposal of record.proposals||[])proposalCard(card,proposal,trip,key);
    }parent.append(card);
  }
  async function deliver(s,record,trip,key) {
    if(s.inFlight||!current(key))return;
    s.inFlight=true;record.status='sending';record.error=null;render();
    try {
      const response=await A.chat(record.payload,record.key);
      const reply=typeof response.reply==='string'?response.reply:response.reply?.text||response.message?.text||response.message;
      if(typeof reply!=='string'||!reply.trim())throw new Error('The assistant did not return a readable reply. Your question is kept; please retry.');
      record.status='sent';if(response.conversation_id)s.conversationId=response.conversation_id;
      const messageId=response.message_id||response.reply?.id||record.key;
      if(!s.messages.some(r=>r.role==='assistant'&&r.messageId===messageId))s.messages.push({role:'assistant',messageId,text:reply,sources:response.sources||[],uncertainty:response.uncertainty||'Confirm live prices, opening hours and transport details with their source before travelling.',as_of:response.as_of,proposals:Array.isArray(response.proposals)?response.proposals:[]});
      s.draft='';
    }catch(error){record.status='failed';record.error=error.message;}
    finally{s.inFlight=false;if(current(key))await render();}
  }
  function proposalCard(parent,proposal,trip,key) {
    const card=U.el('section',null,'ex-proposal');const type=proposal.action_type||proposal.action;card.append(U.el('h4',A.text(proposal.title||'Suggested change')),U.el('p',A.text(proposal.summary||'Review the proposed changes before applying them.')));
    U.lines(card,'Expected changes',proposal.changes);
    if(proposal.timing_impact)card.append(U.el('p','Timing: '+A.text(proposal.timing_impact)));if(proposal.budget_impact)card.append(U.el('p','Budget: '+A.text(proposal.budget_impact)));
    const notice=U.status(card);const preview=U.button('Review proposal',()=>U.busy(preview,notice,async()=>{
      if(!current(key))throw new Error('The selected trip changed. Ask for a fresh proposal.');
      if(!await window.ProfileGate.require()){drawer?.box.close();drawer=null;return;}
      const response=await A.assistantPreview(proposal.id,trip);
      U.confirmation('Confirm assistant suggestion',response.preview||response,{current:()=>current(key)&&allowed(proposal,trip),confirm:token=>A.assistantConfirm(proposal.id,token,trip),done:async result=>{
        proposal.applied=true;if(current(key))await render();
        if(trip&&['record_expense','update_expense','update_budget'].includes(type))window.dispatchEvent(new CustomEvent('experience:expenses-updated',{detail:{tripId:trip}}));
        else if(trip)await window.BudgetExperience?.refreshTrip(trip);
        if(current(key))drawer.notice.textContent=result.message||'The server confirmed the change.';
      }});
    }),'ex-primary');
    preview.disabled=proposal.applied===true||!allowed(proposal,trip);card.append(preview);
    if(proposal.applied)card.append(U.el('p','Applied — confirmed by the server.'));
    else if(preview.disabled)card.append(U.el('p','This proposal is unavailable for the current trip stage. Ordinary planning and expense controls remain available.','ex-muted'));
    parent.append(card);
  }
  function allowed(proposal,trip) {
    const type=proposal.action_type||proposal.action;if(!A.can('assistant_actions')||!actions.has(type)||typeof proposal.id!=='string'||!trip||(proposal.trip_id&&proposal.trip_id!==trip))return false;
    const runtime=window.TripExperience.getSnapshot(trip);if(!runtime)return false;
    if(['record_expense','update_expense'].includes(type))return A.can('expense_tracking')&&proposal.allowed!==false;
    if(['update_budget','apply_budget_option'].includes(type))return runtime.status==='draft'&&proposal.allowed!==false;
    if(runtime.status==='draft')return proposal.allowed!==false;
    return runtime.status==='live'&&proposal.remaining_only===true&&proposal.allowed!==false&&runtime.permitted_actions?.includes('adjust_remaining');
  }
  function clearChat(s,key) {
    if(s.inFlight)return;
    const d=U.dialog('Clear this conversation?','Clearing the view removes on-screen messages only. Server deletion is separate and requires a successful server response.');
    d.actions.prepend(U.button('Clear this view',()=>{sessions.delete(key);d.box.close();if(current(key))render();}));
    if(s.conversationId){const erase=U.button('Delete saved conversation',()=>U.busy(erase,d.notice,async()=>{if(!current(key))throw new Error('The account or trip changed.');await A.clearConversation(s.conversationId);sessions.delete(key);d.box.close();if(current(key)){await render();drawer.notice.textContent='The server confirmed conversation deletion.';}}),'ex-danger');d.actions.prepend(erase);}
  }
  window.addEventListener('hashchange',()=>{visibility();if(drawer)render();});
  window.addEventListener('trip:runtime',()=>{if(drawer)render();});
  window.addEventListener('load',visibility);
  window.RecommendationAssistant={open,allowed};
})();
