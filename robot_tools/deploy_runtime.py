"""Deploy the external runtime/tools using supported backend/profile configuration only.

Never stage this helper inside the external tools directory. Installed package files are read
for integrity checks, never written. Requires --apply; keeps backups and a rollback record.
"""

import argparse
import base64
import subprocess
from pathlib import Path

REMOTE = r'''
import asyncio, base64, hashlib, importlib.metadata, json, os, shutil, subprocess, urllib.request
from datetime import UTC, datetime
from pathlib import Path
import websockets

FILES = __FILES__
BASE = Path('/home/pollen/reachy_tools_runtime')
TOOLS = Path('/home/pollen/reachy_tools')
CONFIG = Path('/home/pollen/.config/reachy_tools/runtime.json')
SERVICE = Path('/home/pollen/.config/systemd/user/reachy-tools-runtime.service')
BACKUP = Path('/home/pollen/reachy_tools_backups') / ('runtime-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ'))

def package_hashes():
    dist = importlib.metadata.distribution('reachy-mini-conversation-app')
    hashes = {}
    bad = []
    for item in dist.files or []:
        if str(item).startswith('reachy_mini_conversation_app/') and str(item).endswith('.py'):
            data = dist.locate_file(item).read_bytes()
            digest = hashlib.sha256(data).digest()
            hashes[str(item)] = digest.hex()
            if item.hash is None or item.hash.mode != 'sha256' or base64.urlsafe_b64encode(digest).rstrip(b'=').decode() != item.hash.value:
                bad.append(str(item))
    if not hashes or bad:
        raise RuntimeError('Installed-source integrity check failed: ' + repr(bad))
    return hashes

def get(route):
    with urllib.request.urlopen('http://127.0.0.1:8000' + route, timeout=5) as response:
        return json.load(response)

def replace(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.runtime-deploy.tmp')
    temporary.write_bytes(content)
    temporary.chmod(mode)
    temporary.replace(path)

async def rpc(method, params):
    async with websockets.connect('ws://127.0.0.1:7860/rpc', open_timeout=8, close_timeout=1) as ws:
        await ws.send(json.dumps({'jsonrpc':'2.0', 'id':1, 'method':method, 'params':params}))
        async with asyncio.timeout(20):
            while True:
                reply = json.loads(await ws.recv())
                if isinstance(reply, dict) and reply.get('id') == 1:
                    if 'error' in reply:
                        raise RuntimeError(method + ': ' + json.dumps(reply['error']))
                    return reply['result']

async def main():
    before = package_hashes()
    status = await rpc('conversation.status', {})
    selected = await rpc('profile_tools.get', {})
    profiles = [selected]
    for profile in selected['profiles']:
        if profile['id'] != selected['profile']:
            profiles.append(await rpc('profile_tools.get', {'profile':profile['id']}))
    BACKUP.mkdir(parents=True, exist_ok=False)
    BACKUP.chmod(0o700)
    record = {'status':status, 'profiles':profiles, 'package_hashes':before}
    replace(BACKUP / 'before.json', json.dumps(record, indent=2).encode())
    destinations = {'conversation_runtime.py':BASE / 'conversation_runtime.py',
                    'voice_look.py':TOOLS / 'voice_look.py', 'speech_control.py':TOOLS / 'speech_control.py'}
    for path in [*destinations.values(), CONFIG, SERVICE]:
        if path.exists():
            target = BACKUP / 'original' / path.relative_to('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    print('backup:', BACKUP, flush=True)
    for name, path in destinations.items():
        data = base64.b64decode(FILES[name])
        compile(data, str(path), 'exec')
        replace(path, data, 0o644)
    config = {'session_url':'https://pollen-robotics-reachy-mini-realtime-url.hf.space/session',
              'hardware_id':get('/api/daemon/status')['hardware_id'],
              'speech_state':'/home/pollen/.config/reachy_tools/speech.json',
              'control_port':8767, 'relay_port':8766}
    replace(CONFIG, json.dumps(config, indent=2).encode())
    unit = """[Unit]
Description=Reachy external quiet/resume and voice-follow realtime relay
After=network-online.target

[Service]
Type=simple
ExecStart=/venvs/apps_venv/bin/python -u /home/pollen/reachy_tools_runtime/conversation_runtime.py --config /home/pollen/.config/reachy_tools/runtime.json
WorkingDirectory=/home/pollen/reachy_tools_runtime
Environment=PYTHONDONTWRITEBYTECODE=1
Restart=on-failure
RestartSec=1
TimeoutStopSec=5
NoNewPrivileges=yes

[Install]
WantedBy=default.target
"""
    replace(SERVICE, unit.encode(), 0o644)
    subprocess.run(['systemctl','--user','daemon-reload'], check=True)
    subprocess.run(['systemctl','--user','enable','reachy-tools-runtime.service'], check=True)
    subprocess.run(['systemctl','--user','restart','reachy-tools-runtime.service'], check=True)
    for attempt in range(20):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8767/health', timeout=1) as response:
                health = json.load(response)
            break
        except OSError:
            await asyncio.sleep(0.25)
    else:
        raise RuntimeError('Runtime did not become healthy; backend configuration not changed')
    # Point at the external relay before reloading the revised tools.
    await rpc('backend.config', {'hf_mode':'local','hf_host':'127.0.0.1','hf_port':8766})
    targets = [p for p in profiles if p['is_active'] or p['profile'] in {'default', 'user_personalities/Marvin'}]
    for profile in sorted(targets, key=lambda p:p['is_active']):
        fresh = await rpc('profile_tools.get', {'profile':profile['profile']})
        enabled = list(fresh['enabled_tools'])
        for name in ['speech_control','voice_look']:
            if name not in enabled:
                enabled.append(name)
        await rpc('profile_tools.save', {'profile':profile['profile'],'enabled_tools':enabled})
        print('tools enabled:', profile['profile'], flush=True)
    after = package_hashes()
    if after != before:
        raise RuntimeError('Installed sources changed during external deployment')
    print('installed Python files unchanged:', len(after), flush=True)
    print('runtime health:', health, flush=True)
    print('user linger:', subprocess.run(['loginctl','show-user','pollen','-p','Linger','--value'], capture_output=True,text=True,check=True).stdout.strip(), flush=True)
    print('deployment complete; live acceptance still required', flush=True)

asyncio.run(main())
'''


def main():
    """Stage external files and configure the existing app through its supported RPC."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", required=True)
    parser.parse_args()
    root = Path(__file__).resolve().parent
    names = ("conversation_runtime.py", "voice_look.py", "speech_control.py")
    files = {name: base64.b64encode((root / name).read_bytes()).decode() for name in names}
    program = REMOTE.replace("__FILES__", repr(files))
    result = subprocess.run(  # noqa: S603 -- fixed remote target, interpreter, stdin source
        ["ssh", "-i", "/Users/simonfrank/.ssh/reachy_ed25519", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
         "pollen@192.168.0.15", "/venvs/apps_venv/bin/python -"],
        input=program, text=True, check=False,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
