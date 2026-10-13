#!/usr/bin/env python3
"""Read-only Chromium checks of Subcontractor/Services UI on an isolated staging URL.

This runner never changes live data. It deliberately refuses the production host.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROUTES = (
    ('Subcontractors', 'app/sourcing/subcontractors/', 'Subcontractors'),
    ('Service Finder', 'app/sourcing/service-finder/', 'Service Finder'),
    ('Services Master', 'app/sourcing/services/', 'Sourcing Services'),
    ('Data Exchange', 'app/sourcing/data-exchange/', 'Sourcing Data Exchange'),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--username', required=True)
    parser.add_argument('--password-env', default='IMS_SOURCING_BROWSER_PASSWORD')
    parser.add_argument('--evidence', default='subcontractor-browser-evidence.json')
    parser.add_argument('--i-confirm-staging-is-isolated', action='store_true', required=True)
    args = parser.parse_args()
    origin = args.base_url.rstrip('/') + '/'
    u = urlparse(origin)
    if u.scheme not in {'http', 'https'} or not u.hostname or u.username or u.password or u.query or u.fragment:
        parser.error('--base-url must be a valid HTTP(S) staging origin with no embedded credentials')
    if u.hostname.lower() in {'ms.sescco.com', 'www.ms.sescco.com'}:
        parser.error('Refusing production ms.sescco.com: browser certification is staging only')
    password = os.getenv(args.password_env, '')
    if not password:
        parser.error('password environment variable is empty: ' + args.password_env)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        parser.error('Playwright is unavailable. Install playwright and Chromium in the staging workstation.')
    evidence = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'origin': origin,
                'suite': 'subcontractor-upgrade-10-staging-browser', 'pages': [], 'errors': []}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 900})
            page = context.new_page()
            page.set_default_timeout(15000)
            page.on('pageerror', lambda error: evidence['errors'].append('JS: ' + str(error)))
            page.goto(urljoin(origin, 'login/'), wait_until='domcontentloaded')
            page.locator('input[name="username"]').fill(args.username)
            page.locator('input[name="password"]').fill(password)
            page.locator('button[type="submit"]').click()
            page.wait_for_load_state('domcontentloaded')
            if '/login/' in page.url:
                raise RuntimeError('Login failed or redirected back to /login/')
            for width in (375, 768, 1440):
                page.set_viewport_size({'width': width, 'height': 900})
                for label, route, heading in ROUTES:
                    url = urljoin(origin, route)
                    response = page.goto(url, wait_until='domcontentloaded')
                    status = response.status if response else 0
                    if status != 200 or '/login/' in page.url:
                        raise RuntimeError(f'{label} at {width}px failed: HTTP {status}, {page.url}')
                    page.get_by_role('heading', name=heading, exact=True).first.wait_for(state='visible')
                    metrics = page.evaluate('''() => ({client: document.documentElement.clientWidth,
                        scroll: document.documentElement.scrollWidth})''')
                    if metrics['scroll'] > metrics['client'] + 2:
                        raise RuntimeError(f'{label}: page-wide horizontal overflow at {width}px: {metrics}')
                    if label == 'Subcontractors':
                        search = page.locator('input[name="q"]')
                        if search.count() != 1:
                            raise RuntimeError('Subcontractor search input missing')
                        if page.get_by_role('link', name='Service Finder').count() < 1:
                            raise RuntimeError('Service Finder link missing')
                    evidence['pages'].append({'label': label, 'width_px': width, 'status': status,
                                              'document_width': metrics['scroll']})
            context.close()
            browser.close()
    except Exception as exc:
        evidence['errors'].append(str(exc))
    result = 'PASS' if not evidence['errors'] and len(evidence['pages']) == 12 else 'FAIL'
    evidence['result'] = result
    Path(args.evidence).write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(f'{result}: {len(evidence["pages"])} staging page+viewport checks; evidence: {args.evidence}')
    for error in evidence['errors']:
        print('ERROR: ' + error, file=sys.stderr)
    return 0 if result == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
