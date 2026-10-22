"""Persistent study sessions and evidence-based learner observations (stdlib only)."""
import copy
import datetime as dt
import json
import re
import uuid

RUN = uuid.uuid4().hex
PATH = 'study/state.json'
STATUSES = ('independent', 'hinted', 'struggled')

def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

def stamp(value):
    return value.isoformat().replace('+00:00', 'Z')

def instant(value):
    if not isinstance(value, str):
        raise ValueError('Use an ISO timestamp with a timezone')
    date = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.tzinfo is None:
        raise ValueError('Timestamps need a timezone')
    return date.astimezone(dt.timezone.utc)

def text(body, field, limit=300, required=True):
    value = body.get(field, '')
    if not isinstance(value, str):
        raise ValueError('Invalid ' + field)
    value = ' '.join(value.split())
    if (required and not value) or len(value) > limit:
        raise ValueError('%s must contain %s1-%s characters' % (field, '' if required else '0 or ', limit))
    return value

def key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{16,32}', value):
        raise ValueError('Invalid study session ID')
    return value

def load(raw):
    if not raw.strip():
        return {'version': 1, 'revision': 0, 'sessions': [], 'observations': [], 'changes': []}
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('version') != 1 or any(not isinstance(data.get(k), list) for k in ('sessions', 'observations', 'changes')):
        raise ValueError('Study data is invalid; restore study/state.json from its history')
    return data

def active(data):
    return next((s for s in data['sessions'] if s['ended_at'] is None), None)

def interrupted(session, at=None):
    at = at or now()
    return bool(session and (session.get('run') != RUN or (at - instant(session['last_seen'])).total_seconds() > 150))

def duration(session, at=None):
    end = session['ended_at'] or (session['last_seen'] if interrupted(session, at) else stamp(at or now()))
    return max(0, int((instant(end) - instant(session['started_at'])).total_seconds()))

def genome(data, at=None):
    at = at or now()
    groups = {}
    for entry in data['observations']:
        if entry.get('retracted_at'):
            continue
        group = groups.setdefault((entry['course'], entry['topic']), [])
        group.append(entry)
    result = []
    for (course, topic), entries in sorted(groups.items()):
        independent = [e for e in entries if e['outcome'] == 'independent']
        days = {e['created_at'][:10] for e in independent}
        recent = sorted(entries, key=lambda e: e['created_at'])[-3:]
        status = 'demonstrated' if len(independent) >= 3 and len(days) >= 2 and all(e['outcome'] == 'independent' for e in recent) else ('needs practice' if recent[-1]['outcome'] == 'struggled' else 'developing')
        age = (at - instant(entries[-1]['created_at'])).days
        confidence = 'low' if age > 21 or len(entries) < 3 else ('high' if len(entries) >= 6 and len({e['session_id'] for e in entries}) >= 3 else 'moderate')
        result.append({'course': course, 'topic': topic, 'status': status, 'confidence': confidence,
                       'count': len(entries), 'last_seen': entries[-1]['created_at'], 'evidence': entries})
    return result

def view(data, at=None):
    at = at or now()
    out = copy.deepcopy(data)
    for session in out['sessions']:
        session['interrupted'] = interrupted(session, at) if session['ended_at'] is None else False
        session['duration_seconds'] = duration(session, at)
    out['active'] = next((s for s in out['sessions'] if s['ended_at'] is None), None)
    out['genome'] = genome(data, at)
    out['server_time'] = stamp(at)
    out['discord_supported'] = __import__('os').name == 'nt'
    return out

def apply(data, body, at=None):
    """Caller serializes read/apply/write. IDs make start/stop/observation retries safe."""
    if not isinstance(body, dict):
        raise ValueError('Study actions must be an object')
    at = at or now()
    data = copy.deepcopy(data)
    action = body.get('action')
    current = active(data)
    session = None
    if action == 'start':
        sid = key(body.get('id'))
        course, topic = text(body, 'course'), text(body, 'topic')
        existing = next((s for s in data['sessions'] if s['id'] == sid), None)
        if existing:
            if (existing['course'], existing['topic']) != (course, topic):
                raise ValueError('Session ID already used for another topic')
            return data
        if current:
            raise ValueError('Stop or recover the current study session first')
        session = {'id': sid, 'course': course, 'topic': topic, 'started_at': stamp(at),
                   'ended_at': None, 'last_seen': stamp(at), 'run': RUN,
                   'discord': {'state': 'pending', 'message': 'Checking Discord…'}}
        data['sessions'].append(session)
    elif action in ('heartbeat', 'continue', 'stop', 'correct_end', 'discord_retry'):
        sid = key(body.get('id'))
        session = next((s for s in data['sessions'] if s['id'] == sid), None)
        if not session:
            raise KeyError(sid)
        if action in ('heartbeat', 'continue'):
            if session['ended_at'] is not None:
                raise ValueError('This session has already ended')
            if action == 'heartbeat' and interrupted(session, at):
                raise ValueError('Recover the interrupted session first')
            session['last_seen'], session['run'] = stamp(at), RUN
        elif action in ('stop', 'correct_end'):
            if action == 'stop' and session['ended_at'] is not None:
                return data
            if action == 'correct_end' and session['ended_at'] is None:
                raise ValueError('Stop the session before correcting its end time')
            fallback = session['last_seen'] if interrupted(session, at) else stamp(at)
            end = instant(body.get('ended_at') or fallback)
            if end < instant(session['started_at']) or end > at:
                raise ValueError('End time must be between start time and now')
            # Do not allow an old session correction to overlap a subsequent session.
            following = data['sessions'][data['sessions'].index(session) + 1:]
            if any(end > instant(s['started_at']) for s in following):
                raise ValueError('The end time overlaps a later study session')
            session['ended_at'] = stamp(end)
        elif session['ended_at'] and session['discord'].get('state') != 'restore_failed':
            raise ValueError('No Discord restoration is pending')
    elif action == 'observe':
        oid = key(body.get('id'))
        if any(e['id'] == oid for e in data['observations']):
            return data
        if body.get('revision') != data['revision']:
            raise ValueError('Your Genome changed. Refresh before adding evidence')
        session = next((s for s in data['sessions'] if s['id'] == body.get('session_id')), None)
        if not session:
            raise ValueError('Evidence must link to a study session')
        outcome = body.get('outcome')
        if outcome not in STATUSES:
            raise ValueError('Choose independent, hinted, or struggled')
        data['observations'].append({'id': oid, 'session_id': session['id'], 'course': session['course'],
             'topic': text(body, 'topic'), 'outcome': outcome, 'evidence': text(body, 'evidence', 2000),
             'source': text(body, 'source', 500, False), 'created_at': stamp(at), 'retracted_at': None})
    elif action == 'retract':
        if body.get('revision') != data['revision']:
            raise ValueError('Your Genome changed. Refresh before retracting evidence')
        entry = next((e for e in data['observations'] if e['id'] == body.get('id')), None)
        if not entry:
            raise KeyError(body.get('id'))
        entry['retracted_at'] = stamp(at)
    else:
        raise ValueError('Unknown study action')
    if action != 'heartbeat':
        data['revision'] += 1
        data['changes'].append({'at': stamp(at), 'action': action, 'id': body.get('id'), 'revision': data['revision']})
    return data

def markdown(data):
    lines = ['# Study sessions', '', '| Course / topic | Started (UTC) | Ended (UTC) | Duration |', '| --- | --- | --- | --- |']
    clean = lambda s: s.replace('|', '\\|').replace('\n', ' ')
    for s in reversed(data['sessions']):
        seconds = duration(s) if s['ended_at'] else None
        lines.append('| %s / %s | %s | %s | %s |' % (clean(s['course']), clean(s['topic']), s['started_at'], s['ended_at'] or 'In progress — confirm interruptions in Brain', '%dm %02ds' % (seconds // 60, seconds % 60) if seconds is not None else 'Running'))
    lines += ['', '# Tutor Genome', '', 'Generated from study/state.json. Add or retract evidence in Brain; this view is rebuilt.', '']
    for node in genome(data):
        lines += ['## %s / %s' % (node['course'], node['topic']), '', '**%s** · %s confidence · %d observations' % (node['status'], node['confidence'], node['count']), '']
        for e in node['evidence']:
            lines.append('- %s · %s · %s (session %s; evidence %s)%s' % (e['created_at'], e['outcome'], e['evidence'], e['session_id'], e['id'], ' · ' + e['source'] if e['source'] else ''))
        lines.append('')
    return '\n'.join(lines) + '\n'
