#!/usr/bin/env python3
"""Authenticated local Brain client for study sessions. Stdlib, no stored token."""
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'start', 'stop', 'heartbeat', 'continue', 'observe', 'retract', 'discord_retry'])
    parser.add_argument('--url', default='http://127.0.0.1:4747')
    for field in ['id', 'course', 'topic', 'session', 'outcome', 'evidence', 'source', 'event', 'ended-at']:
        parser.add_argument('--' + field)
    args = parser.parse_args()
    url = urllib.parse.urlparse(args.url)
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost') or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
        parser.error('Use the local Brain HTTP address')
    base = args.url.rstrip('/')
    # Refuse redirects so the token never follows an external Location header.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *unused, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    html = opener.open(base + '/', timeout=10).read().decode('utf-8')
    match = re.search(r'\bTOKEN\s*=\s*["\']([^"\']+)["\']', html)
    if not match:
        raise ValueError('Brain did not return its local API token')
    def call(body=None):
        request = urllib.request.Request(base + '/api/study', data=json.dumps(body).encode() if body else None,
                                        headers={'X-Brain-Token': match.group(1), 'Content-Type': 'application/json'})
        return json.load(opener.open(request, timeout=45))
    state = call()
    if args.action == 'status':
        result = state
    else:
        body = {'action': args.action, 'id': args.id or uuid.uuid4().hex}
        for field in ['course', 'topic', 'outcome', 'evidence', 'source', 'ended_at']:
            if getattr(args, field) is not None:
                body[field] = getattr(args, field)
        if args.action in ('stop', 'continue', 'heartbeat', 'discord_retry') and not args.id:
            parser.error('--id is required so a stale conversation cannot end a different session')
        if args.action == 'observe':
            body.update(session_id=args.session, revision=state['revision'])
        if args.action == 'retract':
            if not args.event:
                parser.error('--event is required')
            body.update(id=args.event, revision=state['revision'])
        result = call(body)['study']
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read()).get('error', str(exc.code))
        except (ValueError, AttributeError):
            message = 'Brain HTTP error %s' % exc.code
        print('Study: ' + message, file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError) as exc:
        print('Study: ' + str(exc), file=sys.stderr)
        sys.exit(1)
