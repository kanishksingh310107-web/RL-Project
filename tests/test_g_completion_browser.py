"""Real browser checks for multi-day coverage, shopping and the free guide."""
import json
import socket
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright,expect

from test_g_completion import test_generator_does_not_exhaust_places_on_first_two_days as _five_day_scenario


def test_five_day_ui_shopping_and_free_assistant(client,deep_user,monkeypatch):
    from app.database import get_connection
    from main import app
    monkeypatch.setenv('ASSISTANT_MODE','local')
    _five_day_scenario(client,deep_user)
    with get_connection() as conn:
        trip=conn.execute('SELECT id FROM trips WHERE user_id=?',(deep_user,)).fetchone()[0]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    assert server.started
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome');page=browser.new_page(viewport={'width':1280,'height':900})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.route('https://**',lambda route:route.abort())
            account={'user_id':deep_user,'display_name':'Travel tester','has_profile':True,'token':client.headers['Authorization'].split(' ',1)[1]}
            page.add_init_script("localStorage.setItem('rl_travel_user',JSON.stringify("+json.dumps(account)+"));")
            page.goto(f'http://127.0.0.1:{port}/#/trips/{trip}',wait_until='domcontentloaded');page.add_style_tag(content='.hidden{display:none!important}')
            editor=page.locator('#workspaceEditorContainer')
            expect(editor.locator('.te-day-nav button')).to_have_count(5)
            for day in range(1,6):
                editor.locator('.te-day-nav [data-day="'+str(day)+'"]').click()
                expect(editor.locator('.te-stop[data-occurrence]:not([data-occurrence=""])')).not_to_have_count(0)
            # Finalization stays unavailable until required stay details are entered.
            expect(editor).to_contain_text('Accommodation details needed before finalizing.')
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(Path.cwd()/'completion-desktop.png'),full_page=True)
            editor.get_by_role('button',name='Balance all days',exact=True).click()
            expect(page.get_by_role('dialog')).to_contain_text('Review itinerary change')
            page.get_by_role('button',name='Cancel / close',exact=True).click()
            page.locator('#shoppingTab').click();expect(page.locator('#shoppingPane')).to_contain_text('Shopping allowance')
            page.locator('#exAssistantLauncher').click();chat=page.locator('#exAssistantDrawer')
            expect(chat).to_contain_text('No external AI service')
            chat.locator('[name=message]').fill('How much budget remains?');chat.get_by_role('button',name='Send message',exact=True).click()
            expect(chat.locator('.ex-chat-assistant')).to_contain_text('INR 60,000')
            chat.get_by_role('button',name='Close assistant',exact=True).click()
            page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(Path.cwd()/'completion-mobile.png'),full_page=True)
            expect(page.locator('#shoppingPane')).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            assert errors==[],errors
            browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=10)
