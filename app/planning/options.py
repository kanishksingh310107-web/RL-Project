"""Concrete, priced alternatives using the existing catalogue and preview engine."""
import json
import sqlite3
from app.core.cost_model import estimate_cost,activity_fee_inr
from app.database import CONNECTION_OVERRIDE


def activity_budget_options(conn,trip,rows,summary,original_allocations,max_extra):
    from app.itinerary_generator import get_slot_alternatives
    itinerary=conn.execute('SELECT id FROM itineraries WHERE trip_id=?',(trip['id'],)).fetchone()
    if not itinerary:return []
    baseline=estimate_cost(trip,rows)['total']
    choices=[]
    for target in rows:
        if target['status']!='proposed' or target.get('is_pinned') or target.get('is_fixed_booking') or target.get('must_visit') or target.get('planning_priority')=='must_do':continue
        alternatives=get_slot_alternatives(conn,trip['user_id'],itinerary['id'],target['activity_id'])
        for alt in alternatives:
            if alt.get('is_already_scheduled'):continue
            changed=[dict(r,activity_id=alt['id'],title=alt['name'],category=alt['category'],cost_estimate=activity_fee_inr(alt),duration_minutes=alt['duration_minutes']) if r['id']==target['id'] else r for r in rows]
            delta=int(estimate_cost(trip,changed)['total']-baseline)
            total=max(summary['total_budget_inr'],summary['forecast_final_cost_inr']+delta+(0 if summary['emergency_reserve_released'] else summary['emergency_reserve_inr']))
            extra=total-summary['total_budget_inr']
            if extra>max_extra:continue
            allocations={k:{'planned_inr':v,'basis':'total'} for k,v in summary['planned_category_totals_inr'].items()}
            allocations.update({k:dict(v) for k,v in original_allocations.items() if isinstance(v,dict)})
            line=allocations.setdefault('activities',{'planned_inr':0,'basis':'total'})
            line['planned_inr']=max(0,line['planned_inr']+delta);line['basis']='total';line['unit_amount_inr']=line['planned_inr']
            total=max(total,sum(v['planned_inr'] for v in allocations.values()))
            extra=total-summary['total_budget_inr']
            if extra>max_extra:continue
            changes=[{'operation':'swap','target_activity_id':target['id'],'replacement_activity_id':alt['id']},
                {'operation':'budget_allocation','budget_total_inr':total,'budget_allocations':allocations,'budget_reserve_released':summary['emergency_reserve_released']}]
            choices.append({'id':'experience-'+target['id']+'-'+alt['id'],'label':'Lower-cost itinerary' if delta<0 else 'A different experience',
                'total_cost_inr':max(0,summary['forecast_final_cost_inr']+delta),'new_total_budget_inr':total,
                'preview_request':{'operation':'trip_plan','plan_changes':changes},
                'changes':[f"Day {target['day_number']}: replace {target['title']} with {alt['name']}"],
                'benefits':['A concrete alternative from the destination catalogue.'],
                'trade_offs':['A different experience; check current venue availability before booking.'],
                'stays_the_same':['Destination','Dates','Party size','Protected activities and bookings'],
                '_delta':delta})
    choices.sort(key=lambda o:(o['_delta'],o['id']))
    if len(choices)>1:
        selected=[choices[0],choices[-1]] if choices[0]['id']!=choices[-1]['id'] else choices[:1]
    else:selected=choices
    for option in selected:option.pop('_delta',None)
    return selected


async def simulate_option(conn,trip_id,actor,request,proposal):
    from app.trip_preview import AtomicConnection,apply,state
    from app.modules.live import c_call_existing
    clone=sqlite3.connect(':memory:',check_same_thread=False);clone.row_factory=sqlite3.Row
    conn.backup(clone)
    override=CONNECTION_OVERRIDE.set(AtomicConnection(clone))
    try:
        from app.trip_preview import Preview
        await apply(request,trip_id,actor,Preview.model_validate(proposal))
        view=await c_call_existing(request,'GET',f'/api/trip-actions/{trip_id}/timed-view?user_id={actor}')
        _,after,_=state(clone,trip_id)
        scheduled={s['activity_id'] for day in view['days'] for s in day['timeline'] if s['type'] in ('activity','shopping')}
        required={r['activity_id'] for r in after if r['status']!='rejected'}
        if not required.issubset(scheduled):return None
        return {'days':[{'day_number':d['day_number'],'note':d.get('note'),'timeline':[{'title':b['title'],'time_range':b['time_range'],'type':b['type']} for b in d['timeline']]} for d in view['days']]}
    finally:
        CONNECTION_OVERRIDE.reset(override);clone.close()
