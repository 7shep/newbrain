"""Windows desktop UI adapter. Never reads Discord credentials or account APIs."""
import json
import os
import subprocess

def change(mode, previous=None):
    if os.name != 'nt':
        return {'state': 'unavailable', 'message': 'Automatic Discord DND currently needs Windows and the Discord desktop app.'}
    command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File',
               os.path.join(os.path.dirname(__file__), 'study_discord.ps1'), '-Mode', mode]
    if previous:
        command += ['-Previous', previous]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=18,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('Discord desktop controls could not be reached')
        value = json.loads(result.stdout.strip().lstrip('\ufeff'))
        if not isinstance(value, dict) or value.get('state') not in ('dnd', 'restored', 'unchanged', 'unavailable', 'unverified'):
            raise ValueError('Discord returned an unexpected status')
        return value
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'state': 'restore_failed' if mode == 'restore' else 'unavailable',
                'previous': previous, 'message': 'Could not %s Discord status. Open Discord and retry; the study timer is saved.' % ('restore' if mode == 'restore' else 'set')}
