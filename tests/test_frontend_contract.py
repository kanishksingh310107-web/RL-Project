"""Static handler, element and syntax checks for the planner frontend."""
from pathlib import Path
import re
import subprocess


def frontend_sources():
    root = Path(__file__).resolve().parents[1] / 'static'
    files = list(root.rglob('*.js'))
    return root, files, '\n'.join(p.read_text(encoding='utf-8') for p in files)


def test_javascript_syntax():
    _, files, _ = frontend_sources()
    for path in files:
        result = subprocess.run(['node','--check',str(path)],capture_output=True,text=True)
        assert result.returncode == 0, result.stderr


def test_handlers_ids_and_removed_interface():
    root, _, source = frontend_sources()
    html = (root/'index.html').read_text(encoding='utf-8')
    # Include runtime templates: their IDs are installed before their handlers.
    ids = set(re.findall(r'''\bid=["']([^"']+)''',html+'\n'+source))
    uses = set(re.findall(r'''getElementById\(["']([^"']+)["']\)''',source))
    assert not uses-ids, f'Missing IDs: {sorted(uses-ids)}'
    functions = set(re.findall(r'(?:async\s+)?function\s+(\w+)\s*\(',source))
    calls = set()
    for handler in re.findall(r'\bon(?:click|change|submit)="([^"]+)"',html):
        calls.update(re.findall(r'(?<![.\w])([A-Za-z_$][\w$]*)\s*\(',handler))
    assert not calls-functions-{'if','Number','String','parseInt','parseFloat'}
    assert not re.search(r'companionModal|companionHeaderBtn|checkCompanionAccess|refreshLockStatus',source+html)
    assert 'modules/itinerary_editor.js' in html
    for feature in ('editSelectedTrip','deleteSelectedTrip','readTripParty','renderCostBreakdown'):
        assert feature in functions
