# Development setup

Wireless Reachy; VS Code on the Mac through Remote SSH. Files, Python and tests run on Reachy.
Repository: `/home/pollen/projects/reachy-tools`. Documentation index: [README](README.md).

## Open and run

1. Connect VS Code Remote SSH using the existing Mac key:
   `ssh -i ~/.ssh/reachy_ed25519 pollen@192.168.0.15` (use the current IP if changed).
2. Open the repository; select `.venv/bin/python` and install the recommended remote Python/debugger extensions.
3. For development hardware use, stop the dashboard conversation app first, leaving the daemon running.
4. Run **Reachy: conversation app** with F5; stop it afterwards.
5. Forward 7860 for the conversation UI.
6. Telemetry: run `scripts/hub.sh start` on the robot and open `http://reachy-mini.local:8710` in a browser
   on the Mac. It keeps running until `scripts/hub.sh stop` or a restart; `status` shows the address. While
   running it is visible to the home network, transcripts included. **Reachy: telemetry hub** (F5) remains
   for debugging, robot-only through a forwarded port; stop one before starting the other.
   The same script runs on the Mac for the sim (`start`, `stop`, `restart`, `status`; `scripts\hub.bat` on Windows
   runs it in the window): it listens on this machine only, takes `REACHY_HOST` from `.env`, and finds the hub by
   its port, so one you started by hand is managed too. Its log is `~/.local/share/reachy-tools/hub.log`.
   The Linux branch (home-network listening, the robot's own daemon) is unchanged in intent but untested until the
   robot is back; on the robot it now also manages a hub started with F5.

Do not run two conversation apps or competing motion writers.

## Environments and ports

| Setting | Everyday dashboard | Development |
|---|---|---|
| Interpreter | `/venvs/apps_venv/bin/python` | Project `.venv/bin/python` |
| External tools | Project `robot_tools/` | Project `robot_tools/` |
| Configuration | Normal dashboard configuration, including `/venvs/.env` | Project `.env` |
| Instance/tool state | App config and `~/.config/reachy_tools/` | `~/.local/share/reachy-tools-dev/` |
| API keys | `~/.config/reachy_tools/keys/` (shared) | Same |

There is one copy of the tools: the project's `robot_tools/`. `/venvs/.env` holds a single line,
`REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY=/home/pollen/projects/reachy-tools/robot_tools`, so the everyday app
loads the checked-out code when it starts or reloads tools. Keep the checked-out branch working; do
unfinished work on another branch. Never copy tools elsewhere. The former copy, `/home/pollen/reachy_tools/`,
is no longer loaded (switched 2026-10-17; backup of the previous `/venvs/.env` in
`~/.local/share/venvs-env.backup-20261017`).

Packages the tools need beyond the standard library (BeautifulSoup) are pinned in
`robot_tools/requirements.txt` and installed into the app environment with Pollen's own method (that
environment's pip): `scripts/tool_deps.sh install`; `check` confirms. Re-run install if a Pollen update or
reinstall ever replaces `/venvs/apps_venv`. The same pin is in `pyproject.toml` for the development `.venv`.

`.env.example` records development settings. Actual `.env` and mutable state are
excluded from Git. `AUTOLOAD_EXTERNAL_TOOLS=0` avoids directory-wide discovery. There is no relay (retired 2026-10-16).

## Sim (Mac)

Base: `~/Library/Application Support/com.pollen-robotics.reachy-mini/`, managed by the Reachy Mini Control
app (checked 2026-10-19). The sim equivalent of the robot's `/venvs/apps_venv` is **`apps_venv` under that base**.

| What | Path under base | Notes |
|---|---|---|
| Daemon venv | `.venv` | Runs `reachy_mini.daemon.app.main --mockup-sim`; reachy_mini 1.12.0 |
| Apps venv (conversation app runs here) | `apps_venv` | reachy_mini 1.12.0, reachy_mini_conversation_app 1.1.1. Not the project `.venv` |

### Simulator config
The sim app loads **`~/.env`** (the Mac equivalent of the robot's `/venvs/.env`; confirmed working 2026-10-20).
Current settings:

| Variable | Value |
|---|---|
| `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY` | `/Users/simonfrank/Documents/dev/python/reachy-mini/robot_tools` (the project's own folder, as on the robot) |
| `AUTOLOAD_EXTERNAL_TOOLS` | `1` |
| `HF_TOKEN` | set (secret: keep the file `chmod 600`; not in the repo) |

Seen once: `ModuleNotFoundError: reachy_mini.io.jsonrpc` starting the app in sim, though the module exists
in `apps_venv`; cause not found, and it started fine later.

## Windows (not yet tested)

Written but never run on Windows: `scripts\keys.bat` (keys in Credential Manager) and `scripts\hub.bat` (runs the
hub in the window; no background start/stop). Where the Reachy Mini Control app keeps its folders on Windows is not
recorded. Private files (photos, scans) use `chmod`, which does nothing useful there, so they rely on the user
profile's own permissions.

Python 3.12 everywhere (`requires-python` in `pyproject.toml`): the key and hub scripts use the project `.venv`
and stop with a message if it is missing.

## API keys

Keys are stored encrypted, never in Git or plain text: `systemd-creds --user` on the robot, the login Keychain
on the Mac (for the sim), Credential Manager on Windows. Manage them from the project folder, on any, without
sudo: `scripts/keys.sh add tavily` (`scripts\keys.bat` on Windows; paste at the hidden prompt), `check tavily`,
`remove tavily`, and `list` (robot only). `TAVILY_API_KEY` in `~/.env`
also works and wins over the stored key. Details and the accepted limit: [tools: API keys](tools.md#api-keys).

**Versions, 2026-10-16:** dashboard app 1.1.1 / SDK 1.12.0. `pyproject.toml` and `uv.lock` pin hotfix
revision `66141f689e405ae404a5761186057dff183b4f45` (1.1.1); the development `.venv` is still 1.1.0 until synced.
The shared uv cache's clone of the app repository (`~/.cache/uv/git-v0/db/c022d7f344040092`) fails incremental
fetches with `fatal: expected 'acknowledgments'`; fresh clones work. The lock was produced with a temporary
`UV_CACHE_DIR`. Sync with the default cache will hit the same error until that one clone is moved aside.
Compared cached source snapshots: the hotfix changes browser RPC reconnection/history loading and
version metadata, not Python tool interfaces.

The environment synchronisation command is:

```bash
.venv/bin/uv sync --frozen --extra dev --extra hosted --extra robot --link-mode hardlink --no-python-downloads
```

It changes development dependencies, not the running dashboard environment. uv hardlinks reuse cached
package files; do not delete shared caches as cleanup. Free space was about 1.5 GB at initial setup.

## Personalities

```text
workspace/profiles
  → /home/pollen/.config/reachy_mini/conversation_app/user_personalities
      Standard/profile.md
      Marvin/profile.md
```

These are live files, case-sensitive. The workspace link does not move the files or change dashboard selection
(last inspected: `user_personalities/Standard`). Close stale development/lowercase-marvin editor tabs.
The former workspace copies are preserved in `.development/profiles-before-link-20261016T191520/`.

The separate development instance also has a `user_personalities` link to that same directory. Its `.env`
selects `user_personalities/Standard`; saved instance settings may override startup defaults. Its other state
remains separate. Do not also configure this collection as `REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY`, which
would discover it twice. No live personality contents were changed to create these links.

Git records only the absolute symlink, not Standard/Marvin contents. Personality backup remains separate;
the link is specific to this robot's filesystem.

## Sleep and wake word

The `sleep` tool starts the wake watcher (`reachy_wake/`), then runs Pollen's sleep; saying the wake word
("hey mycroft" until "hey Reachy" is trained) starts the conversation app again. In each personality you use,
untick `go_to_sleep` and tick `sleep`. Anything else that puts the robot to sleep (Pollen's app, the inactivity
timeout, a reboot) does not start the watcher: start the app by hand.

The watcher has its own venv. Set it up once (and again if `reachy_wake/requirements.txt` changes):

```bash
cd ~/projects/reachy-tools
.venv/bin/uv venv --python 3.12 ~/venvs/reachy-wake
VIRTUAL_ENV=~/venvs/reachy-wake .venv/bin/uv pip install -r reachy_wake/requirements.txt
```

Logs: `journalctl --user -u reachy-wake`. Status: `systemctl --user status reachy-wake`.

## Tests

**Run Test Task** runs the whole suite, unit and integration. Integration tests need the robot daemon and
conversation app running and fail, saying what to start, if they are not. Commands/results: [test summary](test_summary.md).

## Backups and update procedure

Before changing versions or live paths: record versions, back up code/settings/service definitions, then
review exact changes and rollback. Never patch installed app code or use archived deployers.
Git rollback does not restore mutable settings or undo data migrations.

| Backup | Contents |
|---|---|
| Mac `backups/remote-setup-20261016/` | Source archives, Git bundle and explicitly approved private `robot-live-settings.tar.gz`; owner-only permissions, hash inventory, excluded from Git |
| Robot `/home/pollen/reachy_tools_backups/speaker-mute-20261016T190514/` | Runtime/tool copies before speaker-mute deployment |
| Project `.development/profiles-before-link-20261016T191520/` | Previous authored workspace profiles including pending edits |

Initial migration preserved Git history, uncommitted work and intentional stay_silent deletions; no Mac venv
or SSH private key was transferred. No hosted Git remote was configured by that migration.
Private settings/memory/credentials are not source artifacts and are not copied off the robot without approval.

Explain each consequential command's action, purpose and effect before running it; seek approval outside the
agreed scope. This document is operational guidance, not standing permission for installs or service changes.
