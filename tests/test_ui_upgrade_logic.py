"""Frontend regressions. Deliberately not executed before the integration merge."""
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "static/modules/trip_experience.js"


def js(expression):
    source = """
const vm=require('node:vm'),fs=require('node:fs');
const sandbox={window:{},Intl,Date,AbortController,setTimeout,clearTimeout,URL};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
sandbox.T=sandbox.window.TripExperience;
Promise.resolve(vm.runInContext(process.argv[2],sandbox)).then(value=>process.stdout.write(JSON.stringify(value))).catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
"""
    result = subprocess.run(["node", "-e", source, str(MODULE), expression], capture_output=True, text=True, check=True, cwd=ROOT)
    return json.loads(result.stdout)


@pytest.mark.parametrize("instant,expected", [
    ("2026-11-13T18:29:59Z", "2026-11-13"),
    ("2026-11-13T18:30:00Z", "2026-11-14"),
    ("2026-12-31T20:00:00Z", "2027-01-01"),
])
def test_dates_use_india_midnight(instant, expected):
    assert js(f"T.indiaToday(new Date({json.dumps(instant)}))") == expected


@pytest.mark.parametrize("start,end,field", [
    ("2026-11-13", "2026-11-15", "tripStartDateInput"),
    ("2026-11-15", "2026-11-14", "tripEndDateInput"),
    ("2026-02-30", "2026-11-15", "tripStartDateInput"),
    ("", "2026-11-15", "tripStartDateInput"),
    ("2026-11-15", "bad", "tripEndDateInput"),
    ("2026-11-14", "2027-11-15", "tripEndDateInput"),
])
def test_invalid_dates_have_field_errors(start, end, field):
    assert field in js(f"T.dateErrors({json.dumps(start)},{json.dumps(end)},'2026-11-14')")


def test_same_day_and_past_trip_edit():
    assert js("T.dateErrors('2026-11-14','2026-11-14','2026-11-14')") == {}
    assert js("T.dateErrors('2026-11-10','2026-11-11','2026-11-14',true)") == {}


@pytest.mark.parametrize("status,expected", [
    ("draft", {"pre": True, "live": False, "post": False, "edit": True}),
    ("finalized", {"pre": True, "live": False, "post": False, "edit": False}),
    ("live", {"pre": True, "live": True, "post": False, "edit": False}),
    ("completed", {"pre": True, "live": False, "post": True, "edit": False}),
])
def test_phase_permissions_come_from_runtime(status, expected):
    assert js(f"T.access({{status:{json.dumps(status)}}})") == expected


def test_no_snapshot_fails_closed():
    assert js("T.access(null)") == {"pre": False, "live": False, "post": False, "edit": False}


def test_catalogue_repeats_do_not_share_acceptance():
    result = js("[{id:'day1',activity_id:'same',acceptance_status:'accepted'},{id:'day2',activity_id:'same',status:'accepted'}].map(b=>({id:T.occurrenceId(b),status:T.acceptance(b)}))")
    assert result == [{"id": "day1", "status": "accepted"}, {"id": "day2", "status": "unreviewed"}]


def test_explicit_occurrence_id_takes_priority():
    assert js("T.occurrenceId({itinerary_activity_id:'occurrence',id:'catalogue'})") == "occurrence"


def test_uncalibrated_scores_are_not_inflated():
    assert js("T.matchLabel({match_score:51})") == "Recommended for you"
    assert js("T.matchLabel({score_calibrated:true,calibrated_match_score:89.6})") == "90% preference match"
    assert js("T.matchLabel({score_calibrated:true,calibrated_match_score:101})") == "Recommended for you"


def test_home_area_is_excluded_without_excluding_entire_state():
    profile = "{residence_country:'IN',residence_city:'Pune',residence_state:'Maharashtra'}"
    assert js(f"T.isHomeDestination({{name:'Pune (Maharashtra)'}},{profile})") is True
    assert js(f"T.isHomeDestination({{name:'Mumbai',state:'Maharashtra'}},{profile})") is False
    assert js("T.isHomeDestination({name:'Pune'},{residence_country:'US'})") is False


def test_public_text_and_escaping():
    assert js("T.publicText('LinUCB policy updated')") == "Personalised using your travel preferences and feedback."
    assert js("T.esc('<img src=x onerror=alert(1)>')") == "&lt;img src=x onerror=alert(1)&gt;"


def test_day_progress_is_not_activity_count():
    assert js("T.finishedDays({status:'live',phase:'day_summary',total_days:5,runtime:{current_day:3},runs:[{},{}]})") == 3
    assert js("T.finishedDays({status:'live',phase:'activity',total_days:5,runtime:{current_day:3}})") == 2
    assert js("T.finishedDays({status:'completed',total_days:5})") == 5


def test_api_preserves_readable_validation_errors():
    assert js("fetch=async()=>({ok:false,status:422,json:async()=>({detail:'Lunch duration must be at least 15 minutes.',field:'lunch_duration_minutes'})});T.api('/example').catch(e=>({message:e.message,field:e.field,status:e.status}))") == {
        "message": "Lunch duration must be at least 15 minutes.", "field": "lunch_duration_minutes", "status": 422
    }


def test_api_network_failure_has_retry_guidance():
    result = js("fetch=async()=>{throw new TypeError('network')};T.api('/example').catch(e=>e.message)")
    assert "entries are kept" in result
    assert "retry" in result.lower()


def test_api_keeps_failed_preview_payload_without_applying_it():
    result = js("let requests=[];fetch=async(u,o)=>{requests.push({url:u,body:JSON.parse(o.body)});return {ok:false,status:503,json:async()=>({detail:'Preview unavailable. Please retry.'})}};T.api('/preview',{method:'POST',body:{operation:'swap',target_activity_id:'day2'}}).catch(e=>({requests,message:e.message}))")
    assert result["requests"] == [{"url": "/preview", "body": {"operation": "swap", "target_activity_id": "day2"}}]
    assert "Preview unavailable" in result["message"]
