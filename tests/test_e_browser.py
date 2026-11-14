"""Prompt 5 UI contracts. Write now; execute only after both branches are merged."""
import json

import pytest

from test_ui_upgrade_browser import static_url

playwright=pytest.importorskip('playwright.sync_api')


@pytest.fixture
def experience(static_url):
    flags={key:True for key in ['discovery','budget_options','expense_tracking','itinerary_check','day_options','assistant_chat','assistant_actions']}
    options={'flags':flags,'chat_fails':False,'preview_fails':False,'fail_expense':False,'oversized_budget':False}
    writes=[];expenses=[]
    trip={'id':'trip-1','user_id':'owner','destination_name':'Hampi','destination_id':'hampi_india','start_date':'2099-01-01','end_date':'2099-01-03','duration_days':3,'travellers_count':2,'trip_type':'family','trip_preferences':{}}
    runtime={'trip_id':'trip-1','status':'draft','phase':'draft','runtime':{'current_day':1,'version':1},'total_days':3,'today':[],'schedule':[],'runs':[],'closed_out':False}
    summary={'total_budget_inr':30000,'planned_total_inr':8000,'actual_spending_inr':0,'estimated_remaining_costs_inr':8000,'forecast_final_cost_inr':8000,'available_buffer_inr':22000,'travellers_count':2,'rooms':1,'version':1,
             'allocations':[{'category':'accommodation','amount_inr':8000,'basis':'total','planned_inr':8000,'actual_inr':None,'estimated_remaining_inr':8000}],
             'planned_items':[{'id':'stay-1','category':'accommodation','label':'Stay','estimated_remaining_inr':8000}]}
    destinations=[{'id':key,'name':title,'reasons':['You enjoy heritage walks.'],'estimated_total_inr':20000+index*2000,'match_score':51,'tradeoff':'Busy on weekends','comparison_basis':'3 days · 2 adults','sample_itinerary':[{'day_number':1,'activities':['Heritage walk']}]} for index,(key,title) in enumerate([('hampi_india','Hampi'),('udaipur_mewar_india','Udaipur'),('jaipur_jodhpur_india','Jaipur'),('kerala_alleppey_india','Alleppey')])]
    proposal={'id':'proposal-1','action_type':'update_budget','title':'Use a lower-cost plan','summary':'Review your budget allocation.'}

    def recalculate():
        actual=sum(item['amount_inr'] for item in expenses)
        remaining=0 if any(item.get('payment_state')=='final' for item in expenses) else max(0,8000-actual)
        summary.update(actual_spending_inr=actual,estimated_remaining_costs_inr=remaining,forecast_final_cost_inr=actual+remaining,available_buffer_inr=30000-actual-remaining)
        summary['allocations'][0].update(actual_inr=actual if expenses else None,estimated_remaining_inr=remaining)

    def api(route):
        req=route.request;path=req.url.split('?',1)[0].split('/api/',1)[1];method=req.method
        body=req.post_data_json if req.post_data else None
        if method!='GET':writes.append((method,path,body,req.headers))
        result={};status=200
        if path=='experience/capabilities':result=flags
        elif path=='profile/status':result={'profile_complete':True}
        elif path=='config/google':result={'client_id':''}
        elif path=='trip-experience/capabilities':result={'schedule_preferences_v2':True,'explicit_trip_type':True,'occurrence_acceptance':True,'itinerary_preview':True,'expenses':True,'readonly_sharing':True}
        elif path=='trips/owner':result=[trip]
        elif path in ['trips/owner/feedback-pending','trips/owner/archive']:result=[]
        elif path=='trips/detail/trip-1':result=trip
        elif path=='trips/trip-1/runtime':result=runtime
        elif path=='itinerary/trip-1':result={'id':'itin-1','trip_id':'trip-1','destination_name':'Hampi','total_days':3,'total_estimated_cost':8000,'days':[{'day_number':1,'activities':[]}]}
        elif path=='trip-actions/trip-1/timed-view':result={'trip':trip,'itinerary':{'id':'itin-1'},'days':[{'day_number':1,'theme':'Heritage and sunset','order_explanation':'Nearby stops reduce travel.','total_cost':2000,'timeline':[{'id':'occ-1','activity_id':'place','type':'activity','title':'Heritage walk','time_range':'10:00 – 11:00','cost_estimate':100,'acceptance_status':'unreviewed'}]}]}
        elif path=='recommendations/owner':result={'recommended_for_you':destinations,'trending_trips':[],'seasonal_and_upcoming':[]}
        elif path=='discovery/recommendations':result={'groups':[{'title':'Within your budget','destinations':destinations}]} if method=='GET' else {'destinations':destinations[:3]}
        elif path=='discovery/compare':result={'destinations':[item for item in destinations if item['id'] in body['destination_ids']]}
        elif path=='discovery/feedback':result={'saved':True,'message':'Preference saved.'}
        elif path=='shortlist/owner':result={'is_shortlisted':True}
        elif path=='trips/trip-1/budget':result=summary
        elif path=='trips/trip-1/expenses' and method=='GET':result={'expenses':expenses}
        elif path=='trips/trip-1/expenses' and method=='POST':
            if options['fail_expense']:status,result=422,{'detail':'Check the payment amount.','field':'amount_inr'}
            else:
                record={**body,'id':'expense-1'};expenses.append(record);recalculate();result={'expense':record}
        elif path=='trips/trip-1/expenses/expense-1' and method=='PATCH':expenses[0].update(body);recalculate();result={'expense':expenses[0]}
        elif path=='trips/trip-1/expenses/expense-1' and method=='DELETE':expenses.clear();recalculate();result={'deleted':True}
        elif path=='trips/trip-1/expenses/export':
            route.fulfill(status=200,content_type='text/csv',body='category,amount_inr\nfood,650\n');return
        elif path=='trips/trip-1/budget-options':result={'options':[{'id':'comfort','title':'More comfort','total_cost_inr':50000 if options['oversized_budget'] else 25000,'additional_cost_inr':20000 if options['oversized_budget'] else 5000,'changes':['Better-located stay allowance'],'unchanged':['Dates and party'],'tradeoffs':['Higher spend']}]}
        elif path.endswith('/budget-options/preview') or path.endswith('/day-options/preview') or path.endswith('/itinerary-check/preview') or path=='assistant/proposals/proposal-1/preview':
            if options['preview_fails']:status,result=503,{'detail':'Preview unavailable. Your trip is unchanged.'}
            else:result={'preview':{'token':'preview-token','summary':'Review the changed costs and times.','cost_delta_inr':5000}}
        elif path.endswith('/confirm'):result={'status':'applied','message':'Change confirmed.'}
        elif path=='trips/trip-1/itinerary-check':result={'findings':[{'id':'finding-1','severity':'warning','message':'Travel time is an estimate.','resolutions':[{'id':'fix-1','label':'Review a shorter route'}]}]}
        elif path=='trips/trip-1/day-options':result={'options':[{'id':'day-choice','title':'Less walking','changes':['Fewer transfers'],'total_cost_inr':1800,'cost_delta_inr':-200,'tradeoffs':['One less stop']}]}
        elif path=='assistant/messages':
            if options['chat_fails']:status,result=503,{'detail':'Assistant temporarily unavailable. Retry your message.'}
            else:result={'reply':'<img src=x onerror="window.chatInjected=true"> Here are your options.','conversation_id':'conv-1','message_id':body['idempotency_key'],'proposals':[proposal],'sources':[{'title':'Unsafe source','url':'javascript:alert(1)'}]}
        elif path=='assistant/conversations/conv-1':result={'deleted':True}
        route.fulfill(status=status,json=result)

    with playwright.sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page(viewport={'width':1280,'height':900})
        page.route('**/api/**',api);page.route('https://**',lambda route:route.abort())
        page.goto(static_url+'/static/index.html',wait_until='domcontentloaded');page.add_style_tag(content='.hidden{display:none!important}')
        page.evaluate("state.currentUser={user_id:'owner',display_name:'Test owner',token:'test-token'};localStorage.setItem('rl_travel_user',JSON.stringify(state.currentUser));state.currentProfile={residence_country:'IN',residence_city:'Pune'};state.profileStatus={complete:true};showView('dashboard');")
        playwright.expect(page.locator('#exRecommendationShelves')).to_contain_text('Hampi')
        yield page,options,writes,summary,runtime
        browser.close()


def open_trip(page):
    page.evaluate("location.hash='/trips/trip-1'")
    playwright.expect(page.locator('#workspaceEditorContainer')).to_contain_text('Heritage walk')


def open_budget(page):
    open_trip(page);page.locator('#exBudgetTab').click()
    playwright.expect(page.locator('#exBudgetPane')).to_contain_text('Budget & expenses')


def test_entry_points_honest_scores_and_comparison_limit(experience):
    page,_,writes,_,_=experience
    for name in ['I know my destination','Help me choose','Explore my budget']:
        playwright.expect(page.locator('#exDiscovery').get_by_role('button',name=name,exact=True)).to_be_visible()
    cards=page.locator('#exRecommendationShelves .ex-destination-card')
    playwright.expect(cards.first).to_contain_text('heritage walks')
    playwright.expect(cards.first).not_to_contain_text('90%')
    for index in range(4):cards.nth(index).get_by_role('button',name='Compare',exact=True).click()
    playwright.expect(page.locator('#exComparisonBar')).to_contain_text('3 of 3')
    page.locator('#exComparisonBar').get_by_role('button',name='Compare destinations').click()
    playwright.expect(page.get_by_role('dialog')).to_contain_text('Comparison basis')
    assert len(next(body for _,path,body,_ in writes if path=='discovery/compare')['destination_ids'])==3


def test_discovery_inline_errors_keep_entered_values(experience):
    page,_,writes,_,_=experience
    page.locator('#exDiscovery').get_by_role('button',name='Help me choose',exact=True).click()
    dialog=page.get_by_role('dialog');dialog.locator('[name=origin]').fill('Pune');dialog.locator('[name=start_date]').fill('2020-01-02');dialog.locator('[name=end_date]').fill('2020-01-01');dialog.locator('[name=total_budget]').fill('25000.5')
    dialog.get_by_role('button',name='Find three places for me').click()
    playwright.expect(dialog.locator('[data-error-for=start_date]')).to_contain_text('future')
    playwright.expect(dialog.locator('[data-error-for=total_budget]')).to_contain_text('whole-rupee')
    playwright.expect(dialog.locator('[name=total_budget]')).to_have_value('25000.5')
    assert not any(path=='discovery/recommendations' and method=='POST' for method,path,_,_ in writes)


def test_budget_uses_server_remaining_costs_not_unspent_cash(experience):
    page,_,_,_,_=experience;open_budget(page)
    playwright.expect(page.locator('#exBudgetPane')).to_contain_text('Estimated remaining costs')
    playwright.expect(page.locator('#exBudgetPane')).to_contain_text('22,000')
    playwright.expect(page.locator('#exBudgetPane')).to_contain_text('Not entered')


def test_linked_partial_payment_edit_and_delete(experience):
    page,_,writes,_,_=experience;open_budget(page)
    page.locator('#exBudgetPane').get_by_role('button',name='Add expense',exact=True).click();dialog=page.get_by_role('dialog')
    dialog.locator('[name=amount_inr]').fill('3000');dialog.locator('[name=category]').select_option('accommodation');dialog.locator('[name=planned_item_id]').select_option('stay-1')
    dialog.get_by_role('button',name='Save expense').click()
    playwright.expect(page.locator('#exBudgetPane')).to_contain_text('5,000')
    row=page.locator('#exBudgetPane .ex-expenses li').first;row.get_by_role('button',name='Edit',exact=True).click();dialog=page.get_by_role('dialog')
    dialog.locator('[name=amount_inr]').fill('7500');dialog.locator('[name=payment_state]').select_option('final');dialog.get_by_role('button',name='Save correction').click()
    playwright.expect(page.locator('#exBudgetPane .ex-expenses')).to_contain_text('7,500')
    page.locator('#exBudgetPane .ex-expenses').get_by_role('button',name='Delete',exact=True).click()
    page.get_by_role('dialog').get_by_role('button',name='Delete expense',exact=True).click()
    playwright.expect(page.locator('#exBudgetPane')).to_contain_text('No expenses entered yet.')
    create=next(body for method,path,body,_ in writes if method=='POST' and path.endswith('/expenses'))
    assert create['payment_state']=='partial' and create['planned_item_id']=='stay-1'


def test_failed_expense_has_field_error_and_retains_amount(experience):
    page,options,_,_,_=experience;options['fail_expense']=True;open_budget(page)
    page.locator('#exBudgetPane').get_by_role('button',name='Add expense',exact=True).click();dialog=page.get_by_role('dialog');dialog.locator('[name=amount_inr]').fill('650');dialog.get_by_role('button',name='Save expense').click()
    playwright.expect(dialog.locator('[data-error-for=amount_inr]')).to_contain_text('payment amount')
    playwright.expect(dialog.locator('[name=amount_inr]')).to_have_value('650')
    playwright.expect(dialog.get_by_role('button',name='Save expense')).to_be_enabled()


def test_budget_comparison_cancel_never_confirms(experience):
    page,_,writes,_,_=experience;open_budget(page)
    page.locator('#exBudgetPane').get_by_role('button',name='Explore my budget',exact=True).click();dialog=page.get_by_role('dialog');dialog.locator('[name=max_extra_inr]').fill('5000');dialog.get_by_role('button',name='Compare budget options').click();dialog.get_by_role('button',name='Preview this option').click()
    page.get_by_role('dialog').filter(has=page.get_by_role('heading',name='Review budget option')).get_by_role('button',name='Cancel',exact=True).click()
    assert not any(path.endswith('/confirm') for _,path,_,_ in writes)


def test_itinerary_check_and_better_day_are_previews(experience):
    page,_,writes,_,_=experience;open_trip(page)
    page.get_by_role('button',name='Check my itinerary',exact=True).click();dialog=page.get_by_role('dialog');playwright.expect(dialog).to_contain_text('Travel time is an estimate.');dialog.get_by_role('button',name='Close',exact=True).click()
    page.get_by_role('button',name='Recommend a better day',exact=True).click();dialog=page.get_by_role('dialog');dialog.get_by_role('button',name='Find two alternatives').click();playwright.expect(dialog).to_contain_text('Less walking')
    assert not any(path.endswith('/confirm') for _,path,_,_ in writes)


def test_assistant_reply_is_text_and_retry_reuses_request_key(experience):
    page,options,writes,_,_=experience;options['chat_fails']=True
    page.locator('#exAssistantLauncher').click();chat=page.locator('#exAssistantDrawer');chat.locator('[name=message]').fill('Help me choose');chat.get_by_role('button',name='Send message',exact=True).click()
    playwright.expect(chat).to_contain_text('Assistant temporarily unavailable')
    options['chat_fails']=False;chat.get_by_role('button',name='Retry this message').click()
    playwright.expect(chat.locator('.ex-chat-assistant')).to_contain_text('<img src=x')
    assert chat.locator('.ex-chat-assistant img').count()==0
    assert chat.locator('a[href^="javascript:"]').count()==0
    assert page.evaluate('window.chatInjected===true') is False
    calls=[body for _,path,body,_ in writes if path=='assistant/messages']
    assert len(calls)==2 and calls[0]['idempotency_key']==calls[1]['idempotency_key']


def test_assistant_requires_explicit_confirmation_and_respects_completed_trip(experience):
    page,_,writes,_,runtime=experience;open_trip(page)
    page.locator('#exAssistantLauncher').click();chat=page.locator('#exAssistantDrawer');chat.locator('[name=message]').fill('Suggest a better budget');chat.get_by_role('button',name='Send message',exact=True).click();chat.get_by_role('button',name='Review proposal').click()
    assert not any(path.endswith('/confirm') for _,path,_,_ in writes)
    confirmation=page.get_by_role('dialog').filter(has=page.get_by_role('heading',name='Confirm assistant suggestion'));confirmation.get_by_role('button',name='Cancel',exact=True).click()
    runtime['status']='completed'
    page.evaluate("TripExperience.applySnapshot({tripId:'trip-1'}, {status:'completed',runtime:{current_day:3},total_days:3,closed_out:true})")
    playwright.expect(chat.get_by_role('button',name='Review proposal')).to_be_disabled()


def test_unavailable_assistant_has_no_developer_setup(experience):
    page,options,_,_,_=experience;options['flags']['assistant_chat']=False
    page.evaluate('ExperienceAPI.capabilities(true)');page.locator('#exAssistantLauncher').click()
    playwright.expect(page.locator('#exAssistantDrawer')).to_contain_text('currently unavailable')
    playwright.expect(page.locator('#exAssistantDrawer').get_by_role('button',name='Send message',exact=True)).to_be_disabled()
    assert page.locator('#exAssistantDrawer input[type=password]').count()==0


def test_mobile_keyboard_budget_tab(experience):
    page,_,_,_,_=experience;page.set_viewport_size({'width':390,'height':844});open_trip(page)
    page.locator('#exBudgetTab').focus();page.keyboard.press('Enter')
    playwright.expect(page.locator('#exBudgetPane')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth') is True


def test_double_submit_sends_one_expense_with_an_idempotency_key(experience):
    page,_,writes,_,_=experience;open_budget(page)
    page.locator('#exBudgetPane').get_by_role('button',name='Add expense',exact=True).click();dialog=page.get_by_role('dialog');dialog.locator('[name=amount_inr]').fill('650')
    dialog.locator('form').evaluate("form=>{form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));}")
    playwright.expect(page.locator('#exBudgetPane .ex-expenses')).to_contain_text('650')
    calls=[(body,headers) for method,path,body,headers in writes if method=='POST' and path=='trips/trip-1/expenses']
    assert len(calls)==1
    assert calls[0][0]['idempotency_key']==calls[0][1]['idempotency-key']


def test_out_of_limit_budget_option_is_disabled(experience):
    page,options,_,_,_=experience;options['oversized_budget']=True;open_budget(page)
    page.locator('#exBudgetPane').get_by_role('button',name='Explore my budget',exact=True).click();dialog=page.get_by_role('dialog');dialog.locator('[name=max_extra_inr]').fill('5000');dialog.get_by_role('button',name='Compare budget options').click()
    playwright.expect(dialog).to_contain_text('outside your stated limit')
    playwright.expect(dialog.get_by_role('button',name='Preview this option')).to_be_disabled()


def test_csv_download_and_account_clear(experience):
    page,_,_,_,_=experience;open_budget(page)
    with page.expect_download() as download:
        page.locator('#exBudgetPane').get_by_role('button',name='Download expenses CSV').click()
    assert download.value.suggested_filename=='trip-expenses.csv'
    page.evaluate("state.currentUser=null;showView('auth');")
    playwright.expect(page.locator('#exBudgetPane')).to_be_hidden()
    playwright.expect(page.locator('#exAssistantLauncher')).to_be_hidden()


def test_saved_places_reuse_existing_shortlist_and_refinement_is_explicit(experience):
    page,_,writes,_,_=experience
    card=page.locator('#exRecommendationShelves .ex-destination-card').first
    card.get_by_role('button',name='Save for later',exact=True).click()
    playwright.expect(card.get_by_role('button',name='Saved · remove',exact=True)).to_be_visible()
    assert any(path=='shortlist/owner' for _,path,_,_ in writes)
    card.get_by_role('button',name='Not for me',exact=True).click();page.get_by_role('dialog').get_by_role('button',name='Too expensive',exact=True).click()
    playwright.expect(page.get_by_role('dialog')).to_have_count(0)
    assert any(path=='discovery/feedback' and body['reason']=='too_expensive' for _,path,body,_ in writes)
