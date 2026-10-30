import asyncio, copy, json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path('/tmp/isymotron-audit-20261021-9gqd5ba8')
OUT = ROOT / 'evidence'
OUT.mkdir(exist_ok=True)

async def main():
    results = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width':1440,'height':1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto('http://127.0.0.1:3181/')
        await page.wait_for_load_state('networkidle')
        results['demo_notice'] = await page.locator('.notice-banner').inner_text()
        await page.screenshot(path=str(OUT/'web-demo-desktop.png'),full_page=True)
        await page.set_viewport_size({'width':390,'height':844})
        results['web_mobile_overflow'] = await page.evaluate('document.documentElement.scrollWidth > innerWidth')
        await page.get_by_role('button', name='Abrir chat de ISyMotron').click()
        await page.screenshot(path=str(OUT/'web-chat-mobile.png'),full_page=True)
        results['web_chat_has_composer'] = await page.locator('#gus-chat-drawer textarea').count() > 0
        await page.keyboard.press('Escape')
        results['web_chat_escape_closes'] = await page.locator('#gus-chat-drawer').count() == 0
        await page.close()

        snap = json.loads((ROOT/'backend-state.json').read_text())
        page = await browser.new_page(viewport={'width':1440,'height':1000})
        await page.route('**/api/dashboard',lambda route: route.fulfill(json=snap))
        await page.goto('http://127.0.0.1:3181/')
        await page.wait_for_load_state('networkidle')
        results['real_backend_summary'] = await page.locator('.summary-grid').inner_text()
        results['real_backend_capability'] = await page.locator('.capability-card').first.inner_text()
        results['real_backend_receipts'] = await page.locator('.receipt-entry').all_inner_texts()
        await page.screenshot(path=str(OUT/'web-real-contract.png'),full_page=True)
        await page.close()

        badseal = copy.deepcopy(snap)
        badseal['receipts'][0]['seal_ok'] = False
        badseal['receipts'][0]['host'] = 'win98-retrobox'
        badseal['receipts'][0]['wall'] = 1700000000
        page = await browser.new_page(viewport={'width':1440,'height':1000})
        await page.route('**/api/dashboard',lambda route: route.fulfill(json=badseal))
        await page.goto('http://127.0.0.1:3181/')
        await page.wait_for_load_state('networkidle')
        results['badseal_caption'] = await page.locator('.flow-caption').inner_text()
        results['wrong_host_receipt'] = await page.locator('.receipt-entry').first.inner_text()
        await page.screenshot(path=str(OUT/'web-invalid-seal.png'),full_page=True)
        await page.close()

        page = await browser.new_page(viewport={'width':390,'height':844})
        held = []
        await page.route('**/assets/chat-*.js',lambda route: held.append(route))
        await page.goto('http://127.0.0.1:5181/')
        await page.wait_for_load_state('networkidle')
        await page.get_by_role('button',name='Abrir chat con ISyMotron',exact=True).click()
        await page.get_by_text('Preparando GUS…',exact=True).wait_for()
        for _ in range(40):
            if held: break
            await asyncio.sleep(.05)
        assert held, 'chat chunk was not intercepted'
        await page.get_by_role('button',name='‹ Inicio',exact=True).click()
        results['mobile_left_loading_screen'] = await page.get_by_role('button',name='Abrir chat con ISyMotron',exact=True).count() == 1
        for route in held: await route.continue_()
        await page.get_by_role('heading',name='GUS',exact=True).wait_for()
        results['mobile_loading_forces_navigation_back_to_gus'] = await page.get_by_role('heading',name='GUS',exact=True).count() == 1
        await page.screenshot(path=str(OUT/'mobile-forced-navigation.png'),full_page=True)
        await page.close()

        page = await browser.new_page(viewport={'width':390,'height':844})
        hits = []
        async def fail_chunk(route):
            hits.append(route.request.url)
            await route.abort('failed')
        await page.route('**/assets/chat-*.js',fail_chunk)
        await page.goto('http://127.0.0.1:5181/')
        await page.wait_for_load_state('networkidle')
        await page.get_by_role('button',name='Abrir chat con ISyMotron',exact=True).click()
        await page.locator('.gus-status.error').wait_for()
        await page.get_by_role('button',name='‹ Inicio',exact=True).click()
        await page.unroute('**/assets/chat-*.js',fail_chunk)
        await page.get_by_role('button',name='Abrir chat con ISyMotron',exact=True).click()
        await page.locator('.gus-status.error').wait_for()
        results['mobile_load_failure_persists_after_network_restored'] = await page.locator('.gus-status.error').inner_text()
        results['mobile_chunk_requests_before_retry'] = len(hits)
        await page.close()
        results['web_pageerrors'] = errors
        await browser.close()
    (OUT/'browser-results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False))
    print(json.dumps(results,indent=2,ensure_ascii=False))

asyncio.run(main())
