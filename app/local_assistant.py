"""Free travel help grounded in authenticated project data; no model/network calls."""
import re


async def answer_local(payload,request,actor):
    from app.database import get_connection
    from app.recommendation_budget import _assistant_context,discover_suggestions,DiscoveryInput
    from app.trip_preview import Preview,preview
    from fastapi import HTTPException
    text=payload.message.casefold()
    result={'assistant_mode':'local','model_configured':False,'proposal':None,'preview':None,'confirmation_required':False,'trip_mutated':False,'confirmed_changes':[]}
    with get_connection() as conn:
        profile=conn.execute('SELECT profile_complete,daily_budget_inr FROM user_profile WHERE user_id=?',(actor,)).fetchone()
        companion_row=conn.execute('SELECT companions FROM traveller_profiles WHERE user_id=?',(actor,)).fetchone()
        if not profile or not profile['profile_complete']:
            result['answer']='Start with your basic travel profile and residence, then add past trips or choose no travel history. Complete Deep Personalisation to unlock trip planning. You can return to the questionnaire from the main menu.'
            return result
        context=_assistant_context(conn,actor,payload.trip_id)
        trip=dict(conn.execute('SELECT * FROM trips WHERE id=?',(payload.trip_id,)).fetchone()) if payload.trip_id else None
        runtime=conn.execute('SELECT status FROM trip_runtime WHERE trip_id=?',(payload.trip_id,)).fetchone() if trip else None
        rows=[dict(r) for r in conn.execute('''SELECT ia.* FROM itinerary_activities ia JOIN itineraries i ON i.id=ia.itinerary_id
            WHERE i.trip_id=? AND ia.status!='rejected' ORDER BY ia.day_number,ia.order_index''',(payload.trip_id,))] if trip else []
    money=lambda v:'not entered' if v is None else 'INR '+format(round(v),',')
    if any(word in text for word in ('profile','questionnaire','personalisation','personalization','login','sign in')):
        result['answer']='Complete your basic profile, travel-history choice and every applicable Deep Personalisation question before planning. Google sign-in uses the official account chooser; email and guest sign-in are also available.'
    elif not trip:
        daily=profile['daily_budget_inr'] if profile else None
        companion=str(companion_row['companions'] if companion_row else 'alone').casefold()
        party,trip_type={'alone':(1,'solo'),'solo':(1,'solo'),'partner':(2,'couple'),'friends':(2,'friends'),
            'family_kids':(3,'family'),'family_children':(3,'family'),'family_seniors':(3,'family')}.get(companion,(1,'solo'))
        if type(daily) is not int or daily<=0:
            result['answer']='Add your usual budget per person per day to your basic travel profile to get budget-matched ideas. You can enter an editable whole-party budget in Help me choose.'
            return result
        total=daily*3*party
        query=DiscoveryInput(duration_days=3,comfortable_budget_inr=total,party_size=party,trip_type=trip_type)
        suggestions=discover_suggestions(query,request)
        choices=suggestions['recommendations']
        lines=[f"Here are ideas based on your saved preferences and a suggested INR {daily:,} per person/day × {party} traveller(s) × 3 days = INR {total:,} party allowance. Estimates are indicative; enter a different total for each trip in Help me choose."]
        for place in choices:
            lines.append(place['name']+' — '+money(place['estimated_total_cost_inr'])+'. '+place['why_recommended'][0]+'. Trade-off: '+str(place['trade_off']))
        if not choices:lines.append('No catalogue destination fits this estimated allowance. Open Help me choose to adjust your dates, travellers or whole-party budget.')
        result['answer']='\n\n'.join(lines)
    elif any(word in text for word in ('budget','expense','spend','spent','cost','cheaper','money','₹')):
        budget=context['budget']
        lines=[f"For {trip['destination_name']}: total budget {money(budget['total_budget_inr'])}; recorded spending {money(budget['actual_total_inr'])}; estimated remaining costs {money(budget['estimated_remaining_costs_inr'])}; forecast {money(budget['forecast_final_cost_inr'])}.",
            'Protected emergency reserve: '+money(budget['emergency_reserve_inr'])+'. Available buffer after protected reserve: '+money(budget['available_buffer_inr'])+'.',
            'Open Budget & expenses to explore complete plan alternatives or record a payment. A deposit reduces the remaining estimate; mark a linked final payment only when no further payment is expected.']
        if not budget['forecast_complete']:lines.append('Some category estimates are missing, so the forecast is incomplete.')
        if 'shopping' in text:lines.append('The Shopping tab shows reserved shopping time, allowance and recorded spending.')
        result['answer']='\n\n'.join(lines)
    elif any(word in text for word in ('remove','skip','downtime','relax','running late','too busy','less walking','swap','replace')):
        movable=[r for r in rows if r['status']=='proposed' and not r.get('is_pinned') and not r.get('is_fixed_booking') and not r.get('must_visit') and r.get('planning_priority')!='must_do']
        target=next((r for r in movable if r['title'].casefold() in text),movable[-1] if movable else None)
        if runtime and runtime['status']!='draft':
            result['answer']='Your saved trip stage protects the itinerary. During a live trip, use Adjust remaining itinerary to preview a change to upcoming activities. Completed trips stay read only. Expense corrections remain available in Budget & expenses.'
        elif not target:
            result['answer']='There is no unreviewed, unpinned activity I can safely suggest changing. Use the itinerary controls to review your choices; accepted stops and bookings are protected.'
        else:
            proposal={'operation':'remove','target_activity_id':target['id']}
            if any(word in text for word in ('swap','replace')):
                from app.itinerary_generator import get_slot_alternatives
                with get_connection() as conn:
                    alternatives=get_slot_alternatives(conn,actor,target['itinerary_id'],target['activity_id'])
                alt=next((a for a in alternatives if not a.get('is_already_scheduled')),None)
                if alt:proposal={'operation':'swap','target_activity_id':target['id'],'replacement_activity_id':alt['id']}
                else:
                    result['answer']='No suitable unused replacement is available in the current catalogue. Try Recommend a better day or add a custom activity.'
                    return result
            if 'less walking' in text:
                proposal={'operation':'preferences','preferences':{'intensity':trip.get('travel_pace') or 'balanced','walking_limit_km':0,'accessibility_notes':'Prefer vehicle transfers','transport_mode':'cab','priorities':[]}}
            try:
                prepared=await preview(payload.trip_id,Preview.model_validate(proposal),request)
                result.update(proposal=proposal,preview=prepared,confirmation_required=True)
                result['answer']='I prepared a proposed change for you to review. Nothing in your trip has changed. Check the full timetable and cost impact, then confirm only if it suits you.'
            except HTTPException:
                result['answer']='I could not prepare a safe change against the current itinerary. Your trip is unchanged. Open the itinerary to review the available alternatives.'
    elif any(word in text for word in ('day','schedule','itinerary','today','plan','empty','blank')):
        with get_connection() as conn:
            slots=[dict(r) for r in conn.execute('SELECT * FROM timed_itinerary_slots WHERE trip_id=? ORDER BY day_number,order_index',(payload.trip_id,))] if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='timed_itinerary_slots'").fetchone() else []
        lines=[f"Your {trip['duration_days']}-day trip to {trip['destination_name']} runs from {trip['start_date']} to {trip['end_date']}."]
        for day in range(1,trip['duration_days']+1):
            stops=[s for s in slots if s['day_number']==day and s['slot_type'] in ('activity','shopping')]
            lines.append('Day '+str(day)+': '+('; '.join(s['start_time']+' '+s['title'] for s in stops) if stops else 'No attraction currently fits. Check the day note, departure window and available catalogue places.'))
        lines.append('Balance all days can redistribute proposed activities with a preview. It keeps accepted stops and pinned bookings in place. Travel times and venue details are estimates.')
        result['answer']='\n\n'.join(lines)
    elif any(word in text for word in ('why','recommend','like','quieter','quiet')):
        result['answer']='Your recommendations use your stated interests, trip context, previous ratings and revisit choices. Your home city is excluded. Use Interested, Not for me and More like this to refine the choices. Quieter-place labels come from catalogue descriptions, not live crowd measurements.'
    else:
        result['answer']='I can help explain your itinerary, review your saved budget, find destination ideas, or prepare a safe change for confirmation. Try “Explain my itinerary”, “How much budget remains?”, “Suggest more downtime” or “Help me choose a destination”. This free guide uses project data and does not invent live bookings, prices or conditions.'
    return result
