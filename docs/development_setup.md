# Development setup

Wireless Reachy; VS Code on the Mac through Remote SSH. Files, Python and tests run on Reachy.
Repository: `/home/pollen/projects/reachy-tools`. Documentation index: [README](README.md).

## Open and run

1. Connect VS Code Remote SSH using the existing Mac key:
   `ssh -i ~/.ssh/reachy_ed25519 pollen@192.168.0.15` (use the current IP if changed).
2. Open the repository; select `.venv/bin/python` and install the recommended remote Python/debugger extensions.
3. For development hardware use, stop the dashboard conversation app first, leaving the daemon running.
4. Run **Reachy: conversation + runtime** with F5; stop the whole compound afterwards.
5. Forward 7860 for the conversation UI and 8710 for the optional **Reachy: telemetry hub**.

Do not run two conversation apps or competing motion writers. The everyday runtime can stay up on its
separate ports. **Reachy: conversation app** alone needs its runtime already running.

## Environments and ports

| Setting | Everyday dashboard | Development |
|---|---|---|
| Interpreter | `/venvs/apps_venv/bin/python` | Project `.venv/bin/python` |
| External tools | `/home/pollen/reachy_tools/` | Project `robot_tools/` |
| Runtime source | `/home/pollen/reachy_tools_runtime/conversation_runtime.py` | Project `robot_tools/conversation_runtime.py` |
| Configuration | Normal dashboard configuration, including `/venvs/.env` | Project `.env` and `.development/runtime.json` |
| Relay/control ports | 8766/8767 | 8786/8787 |
| Instance/tool state | App config and `~/.config/reachy_tools/` | `~/.local/share/reachy-tools-dev/` |

`.env.example` records development settings. Actual `.env`, runtime configuration and mutable state are
excluded from Git. `AUTOLOAD_EXTERNAL_TOOLS=0` avoids directory-wide discovery. Editing project tool
source does not automatically update the everyday installed copies. The everyday relay is supervised by
`reachy-tools-runtime.service`; development processes are launched on demand.

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

## Tests

**Run Test Task** runs the maintained unit suite. The separate all-unit task includes the experimental tracker.
Live integration tests require deliberate selection. Commands/results: [test summary](test_summary.md).
The offline workbench uses fake peers and speaker hardware, not real speech recognition, playback or movement.

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
