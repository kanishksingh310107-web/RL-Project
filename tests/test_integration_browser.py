"""Exercise the actual browser and FastAPI app together on an isolated database."""
import socket
import threading
import time

import pytest
import uvicorn

from test_integration_upgrade import planned


def test_browser_against_real_trip_apis(client,deep_user):
    from playwright.sync_api import sync_playwright, expect
    from main import app
    trip,_=planned(client,deep_user)
    token=client.headers['Authorization'].split(' ',1)[1]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.05)
    assert server.started,'The isolated browser test server did not start.'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome')
            page=browser.new_page(viewport={'width':1280,'height':900})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.route('https://**',lambda route:route.abort())
            page.add_init_script("localStorage.setItem('rl_travel_user',JSON.stringify("+__import__('json').dumps({'user_id':deep_user,'display_name':'Integration tester','has_profile':True,'token':token})+"));")
            page.goto(f'http://127.0.0.1:{port}/#/trips/{trip["id"]}',wait_until='domcontentloaded')
            page.add_style_tag(content='.hidden{display:none!important}')
            expect(page.locator('#workspaceEditorContainer [data-occurrence]')).not_to_have_count(0)
            first=page.locator('#workspaceEditorContainer [data-occurrence]').filter(has=page.locator('[data-choice=accept]')).first
            first.locator('[data-choice=accept]').click()
            expect(page.locator('#workspaceEditorContainer')).to_contain_text('1 of')
            first=page.locator('#workspaceEditorContainer [data-occurrence]').filter(has=page.locator('[data-edit=pin]')).first
            first.locator('[data-edit=pin]').click()
            expect(page.get_by_role('dialog')).to_be_visible()
            page.get_by_role('button',name='Confirm change',exact=True).click()
            expect(page.locator('#workspaceEditorContainer')).to_contain_text('Fixed booking / pinned')
            page.locator('[data-undo]').click()
            expect(page.locator('#workspaceEditorContainer')).not_to_contain_text('Fixed booking / pinned')
            page.locator('[data-expenses]').click()
            expense=page.get_by_role('dialog')
            expense.locator('[name=description]').fill('Lunch expense')
            expense.locator('[name=amount]').fill('650')
            expense.locator('[name=category]').select_option('food')
            expense.get_by_role('button',name='Save expense').click()
            expect(expense.locator('[data-summary]')).to_contain_text('650')
            expense.get_by_role('button',name='Cancel / close').click()
            page.locator('[data-share]').click()
            share=page.get_by_role('dialog')
            share.get_by_role('button',name='Create read-only link').click()
            expect(share.locator('[data-result] a')).to_have_count(1)
            public_url=share.locator('[data-result] a').get_attribute('href')
            public=page.request.get(public_url)
            assert public.status==200
            assert 'user_id' not in public.json()['trip']
            share.get_by_role('button',name='Revoke links').click()
            expect(share.locator('[data-result]')).to_contain_text('All sharing links revoked.')
            assert page.request.get(public_url).status==404
            share.get_by_role('button',name='Cancel / close').click()
            page.reload(wait_until='domcontentloaded');page.add_style_tag(content='.hidden{display:none!important}')
            expect(page.locator('#workspaceEditorContainer')).to_contain_text('1 of')
            expect(page.locator('#wsTabBtn-live')).to_be_disabled()
            page.set_viewport_size({'width':390,'height':844})
            page.get_by_role('link',name='Back to main menu').click()
            expect(page.locator('#dashboardView')).to_be_visible()
            page.go_back()
            expect(page.locator('#tripExperienceView')).to_be_visible()
            page.set_viewport_size({'width':1280,'height':900})
            page.get_by_role('button',name='Finalize itinerary',exact=True).click()
            page.get_by_role('button',name='Start trip',exact=True).click()
            for _ in range(60):
                saved=client.get(f"/api/trips/{trip['id']}/runtime?user_id={deep_user}").json()
                if saved['status']=='completed':break
                version=saved['runtime']['version']
                if saved['phase']=='activity':
                    page.locator('[data-c-end]').click()
                elif saved['phase']=='activity_review':
                    review=page.locator('[data-c-review] form')
                    for rating in review.locator('[data-rating]').all():rating.select_option('4')
                    review.locator('[name=action]').select_option('keep')
                    review.get_by_role('button',name='Save review and continue').click()
                elif saved['phase']=='awaiting_day_end':
                    page.locator('[data-c-close-day]').click()
                elif saved['phase']=='day_summary':
                    page.locator('[data-c-next]').click()
                else:
                    pytest.fail('Unexpected live phase: '+saved['phase'])
                page.wait_for_function("args=>{const s=TripExperience.getSnapshot(args.id);return s&&s.runtime.version>args.version}",arg={'id':trip['id'],'version':version})
            assert saved['status']=='completed'
            post=page.locator('#workspacePostContainer form')
            expect(post).to_be_visible()
            for rating in post.locator('[data-rating]').all():rating.select_option('4')
            post.locator('[name=would_revisit]').select_option('yes')
            post.locator('[name=liked]').fill('Heritage walks')
            post.locator('[name=disliked]').fill('Busy roads')
            expect(post.locator('[name=trip_type]')).to_have_value('family')
            post.get_by_role('button',name='Submit and close out trip').click()
            expect(page.locator('#workspacePostContainer')).to_contain_text('feedback saved')
            expect(page.locator('#wsTabBtn-live')).to_be_disabled()
            page.get_by_role('link',name='My trips',exact=True).click()
            expect(page.locator('#teTripList')).to_contain_text('Past trips')
            expect(page.locator('#teTripList')).to_contain_text('Feedback saved')
            assert errors==[],errors
            browser.close()
    finally:
        server.should_exit=True;thread.join(timeout=10)
