# Developing on Reachy through VS Code

This is the main setup and migration guide for our project. The agreed direction is to keep the
project on the Wireless Reachy and edit, run and debug it through VS Code Remote SSH on the Mac.
The development copy and isolated environment were prepared on 2026-10-16. Everyday operation still
uses its existing tools and service; no live switch, app restart or hardware conversation test was performed.

The official conversation app remains unmodified. Our tools and profiles live outside its installed
package. Do not restore the retired app patches, monkey-patch the app or add a competing motor writer.

## Where development happens

VS Code's window runs on the Mac. Remote SSH opens a folder on Reachy; files, the Python interpreter,
tests and the app run on Reachy. VS Code installs its server component there. A full desktop VS Code
installation on the robot is unnecessary.

Pollen explicitly documents Remote SSH and recommends keeping the source repository on the robot:
[Wireless development workflow](https://github.com/pollen-robotics/reachy_mini/blob/main/docs/source/platforms/reachy_mini/development_workflow.md).
Microsoft documents [remote editing, debugging and port forwarding](https://code.visualstudio.com/docs/remote/ssh).

Our additional recommendation is to separate development code, dependencies and settings from the
everyday app. That separation protects the working setup while we test changes.

## Project layout

Repository root: `/home/pollen/projects/reachy-tools/`. This is our project, not a copy or fork
of Pollen's SDK. Preserve the existing project's Git history where possible; a new folder name does
not require a new Git repository. Check the existing remote before creating another one.

```text
/home/pollen/projects/reachy-tools/
    robot_tools/       Our Python tools, companion runtime and existing helpers
    reachy_hub/        Our telemetry/browser interface, including static assets
    profiles/         Authored personality definitions
    docs/             Setup, architecture, tools, roadmap and test evidence
    tests/
        unit/         Tests that do not require a live robot
        integration/  Tests that deliberately connect to a robot
        data/         Reviewed fixtures used by tests
    .vscode/          Remote launch, interpreter and test configuration
    pyproject.toml    Project metadata, commands and dependencies
    uv.lock           Locked app, SDK, project and development dependencies
    .gitignore
    AGENTS.md         Project instructions
    .venv/            Robot development environment; excluded from Git
```

Docs and tests belong in this same repository. They are available in the remote VS Code window and
are backed up with the code. They are not installed into the conversation app's `site-packages`.
Keep plans such as `robot_tools/plan.md` and `reachy_hub/plan.md` with their components.

`robot_tools/` currently mixes actual tools with runtime and deployment helpers. Before configuring
discovery, check the loader for the selected app release and expose only the intended tool modules.
Do not enable directory-wide autoload over this mixed directory. Any required layout/import changes
must be reviewed and tested before activation.

## Open the project in VS Code

1. On the Mac, install Microsoft's **Remote - SSH** extension if it is not already installed.
2. Open the Command Palette with **Cmd+Shift+P**, select **Remote-SSH: Add New SSH Host...**, and enter:
   ```text
   ssh -i ~/.ssh/reachy_ed25519 pollen@192.168.0.15
   ```
   Save the entry in the SSH configuration offered by VS Code. This uses the existing Mac key; do not
   copy that private key to the robot. If an equivalent host entry already exists, use it instead.
3. Select **Remote-SSH: Connect to Host...** and choose that host. Select **Linux** if asked. VS Code
   opens a remote window and installs its server component on Reachy on first connection.
4. In that window choose **File > Open Folder...** and enter `/home/pollen/projects/reachy-tools/`.
5. Install the recommended Python and Python Debugger extensions **on the SSH host** when prompted.
   The project selects `.venv/bin/python`; its terminal, tests, files and debugger now run on Reachy.

Use the router's current robot IP if it changes. `reachy-mini.local` can also be used when local name
resolution works. Closing the old Mac project does not delete it or its backups.

## Saved configuration: no manual exports

| Launch | External tools | Configuration |
|---|---|---|
| Everyday dashboard app | `/home/pollen/reachy_tools/` | Existing `/venvs/.env`; inspected and left unchanged |
| Development app | `/home/pollen/projects/reachy-tools/robot_tools/` | Project `.env`, loaded by VS Code and by the app when run from this folder |

The project `.env` also selects `profiles/development/`, separate instance/tool state beneath
`/home/pollen/.local/share/reachy-tools-dev/`, and relay/control ports **8786/8787**. Everyday runtime
ports remain **8766/8767**. `AUTOLOAD_EXTERNAL_TOOLS=0` keeps helper scripts out of tool discovery.
The two development adapters accept `REACHY_TOOLS_CONTROL_PORT`; their unchanged default is 8767.

`.env.example` is tracked as a configuration reference. The actual `.env`, `.development/runtime.json`
and local agent context are excluded from Git. Saved files survive closing VS Code and rebooting;
development processes start when requested, not automatically at boot. Reboot behaviour was not tested.

The environment contains SDK **1.12.0** and conversation app **1.1.0**, pinned to the actual installed
Hugging Face source commit **231a8591c8a99b7c25bbd62ffb5645f2ace851f3**. The version number alone is not
sufficient to identify that app source. Recreate/synchronise the environment, when needed, from the project:

```text
.venv/bin/uv sync --frozen --extra dev --extra hosted --extra robot --link-mode hardlink --no-python-downloads
```

The isolated environment reuses immutable cached package files through uv hardlinks; its dependency
selection and installed package metadata are separate from the dashboard app. There was approximately
**1.5 GB free** after installation. Do not delete shared caches or change live dependencies as part of cleanup.

## Migration table

The Mac source root below is `/Users/simonfrank/Documents/dev/python/reachy-mini/`.
The repository source has been copied to Reachy; the table also records what remains outside it.
Destinations below the repository are relative to `/home/pollen/projects/reachy-tools/`.

| Current files or component | Destination | Action |
|---|---|---|
| Mac `robot_tools/__init__.py`, `today.py`, `location.py`, `speech_control.py`, `voice_look.py` | Repository `robot_tools/` | Copied. Original tool files matched the live versions before the development-only control-port setting was added. Live files were not replaced. |
| Mac `robot_tools/conversation_runtime.py` | Repository `robot_tools/` | Copied; the development launch uses its separate configuration and ports. |
| Mac deployment/install/check helpers in `robot_tools/` | Same relative paths in the repository initially | Preserve for review/history. Retired patch installers remain retired; migration does not execute any helper. |
| Mac `reachy_hub/`, including `static/index.html` and component plan | Repository `reachy_hub/` | Copied. Tracking experiments remain separate from the active tools. |
| Mac `profiles/marvin/profile.md` | Repository `profiles/marvin/profile.md` | Copied as source. Live persona/voice/settings were not overwritten. Development uses a separate development profile. |
| Mac `docs/`, including this guide | Repository `docs/` | Copy maintained documentation; retain historical evidence with accurate labels. |
| Mac `tests/unit/`, `tests/integration/`, `tests/data/` and package markers | Repository `tests/` | Copied, with deliberate live tests kept separate from ordinary test discovery. |
| Mac `.vscode/launch.json`, `settings.json`, `tasks.json`, `extensions.json` | Repository `.vscode/` | Configured for the actual app, development runtime, hub and robot interpreter. |
| Mac `pyproject.toml`, `.gitignore`, `.env.example`, `AGENTS.md`, `CLAUDE.md`, root/component plans | Same relative paths in repository | Preserve project metadata and instructions. Local agent notes identify the new remote workflow. |
| Mac `.claude/skills/` and relative links in `skills/` | Same relative paths in repository | Copy both targets and links so project instructions remain usable on Linux. |
| Existing Git history and reviewed working changes | Repository on Reachy, source archive and Git bundle on Mac | Preserve history and make a robot development checkpoint. No hosted Git remote is configured yet; do not describe a Mac backup as an automatic remote backup. |
| `uv.lock` | Repository root | Created and successfully installed with `--frozen`. |
| Mac `.venv` and its external environment | Remain on Mac | Do not transfer. Create a Linux/ARM development environment on Reachy. |
| Official conversation app and SDK | Robot development `.venv/` | Install compatible, fixed versions. Do not copy installed Mac packages or alter the dashboard app's environment. |
| Existing robot `/home/pollen/reachy_tools/` | Leave in place during migration | Back up and compare. It remains the working external-tools location until a tested switch is approved. |
| Existing robot `/home/pollen/reachy_tools_runtime/` | Leave in place during migration | Back up the runtime and record the actual executable/configuration paths before replacing anything. |
| Existing `~/.config/systemd/user/reachy-tools-runtime.service` on robot | Leave in place during migration; preserve a private backup | Record its dependencies and interpreter. Review before any service change; do not start a second runtime on its ports. |
| Existing robot `~/.config/reachy_tools/` and actual app instance data | Leave in place initially; back up privately off the robot | Preserve settings, memory, tool selections and state. Discover actual paths rather than assuming defaults. |
| Development settings and runtime state | `/home/pollen/.local/share/reachy-tools-dev/` | Created separately and configured explicitly; excluded from Git. |
| Tokens, `.env` files, private keys, personal memory and sensitive logs | Protected configuration/backup locations outside the source repository | Do not commit or blindly copy. Do not copy the Mac's private SSH keys onto Reachy. |
| Generated caches, `.workbench/` receipts/artifacts, logs and build outputs | Leave out of source transfer | Recreate when needed. A saved check receipt is not proof that the transferred environment passes. |
| Mac `reachy_workbench/` and its tests | Repository as optional diagnostic code, pending review | Preserve existing work without making it the required launcher or deployment system. Its fake peers are not the real app. |

## Transfer without replacing the working setup

1. With approval, inventory the robot read-only: actual source/configuration paths, active personality,
   app/SDK versions, service commands, ports, storage and available memory. Compare its files with the Mac.
2. Back up both the Mac working tree and the robot's current code, settings and service definitions.
   Copy the robot backup off the robot. Protect backups containing credentials or personal data.
3. Review the complete Git changes, including untracked files and intentional deletions. Check for secrets
   and private recordings. For this initial transfer, use the original Git history bundle plus an explicit
   source snapshot/manifest, preserving uncommitted work and deletions in the new development checkpoint.
4. Verify the transferred files against the manifest. Do not overwrite existing live directories or use
   deletion-based syncing into them. Configure a private hosted Git remote separately when its destination
   is agreed; none was present in the Mac repository.
5. Create the robot development environment, fix dependency versions and configure separate instance data
   and the intended external tools. Include every service needed by those tools, not just the app executable.
6. Run automated checks, then arrange a hardware test. Stop the normal conversation app while testing the
   development app; leave the daemon running. Avoid duplicate runtimes, occupied ports and competing motion.
7. After acceptance, review the exact live-path/service/settings changes and restoration steps. Only then
   switch everyday operation to the tested revision. Keep the Mac backup and previous working setup.

The Mac working tree retains its existing uncommitted changes. A plain clone of its original HEAD alone
would omit untracked work and restore deleted files. The initial transfer therefore included the reviewed
working source as well as Git history, with the two intentional `stay_silent` deletions preserved.

Source backups belong in Mac `backups/remote-setup-20261016/` and are excluded from Git. Copying the robot's
private settings, memory and `.env` to that Mac location was blocked by automatic approval review pending
specific consent. No private configuration backup was transferred; live settings were left unchanged.

## Run, test and debug

Select the robot project's Python interpreter in the remote VS Code window. Provide ordinary Run and Debug
configurations for the real conversation app and required companion runtime, with their output visible.
Do not hide startup, dependency installation or deployment inside pasted remote programs.

For a hardware session, first stop the normal conversation app in Reachy Mini Control, leaving the daemon
running. In **Run and Debug**, select **Reachy: conversation + runtime** and press **F5**. This launches the
actual app and the development relay; it can use the microphone, speaker and move the robot. Stop the whole
compound when finished. The existing everyday runtime service can stay running on its different ports.
The conversation launch alone requires the development runtime to be running already.

Use VS Code's **Ports** panel to forward 7860 and open the conversation UI. The optional **Reachy: telemetry
hub** launch uses port 8710. **Run Test Task** defaults to the named maintained suite, explicitly excluding
the experimental tracker file. A separate task runs all unit tests including that file; the Testing panel
also discovers all unit tests. Live integration tests are not part of these unit tasks.

Once installed and configured, the app's documented command is:

```text
reachy-mini-conversation-app --ui --debug
```

Forward robot port 7860 through VS Code to open the app UI in the Mac browser. The current app also
documents external tool/profile directories and `REACHY_MINI_INSTANCE_PATH` for separate instance data.
Verify these options against the exact release being installed; current upstream documentation can be
ahead of the robot's installed version. Saved UI settings can override environment defaults.
[Conversation app documentation](https://github.com/pollen-robotics/reachy_mini_conversation_app#readme).

Automated checks cover our code, imports and compatibility with the chosen real app version. Keep
experimental tracker failures visible and separate from maintained checks; do not silently exclude new
failures. Live integration tests must require deliberate selection and an explicit target robot.

Hardware acceptance covers actual spoken input, audible output, quiet plus spoken resume, speaker following,
gestures and return to following, app restart, and reboot/service startup. Test ordinary conversation before
and after our features. A transcript, successful deployment or passing unit suite alone is insufficient.

The existing workbench can exercise relay events with simulated peers. It does not run real speech
recognition, synthesis or physical motion and cannot substitute for this acceptance test. Its zipapp build
and the existing `deploy_runtime.py` are not the agreed migration mechanism. The latter embeds a remote
program, lacks transactional rollback and borrows the app interpreter; do not run it for this migration.

Verification on Reachy, 2026-10-16:

- **170 maintained unit/transport tests passed**, excluding only `tests/unit/test_tracker.py` (the previously
  documented experimental suite). Two upstream Python/GObject deprecation warnings were reported.
- The real app loaded today, location, speech_control, voice_look, move_head and sweep_look from the selected
  profile, with stock task_status/task_cancel added by its registry. No tools were called during that check.
- Development runtime health and both adapters worked on 8787 with zero cloud sessions; the test process
  was stopped afterward. It did not change speech state or contact the actual conversation app.
- Hardware conversation, audible output, tracking accuracy, the VS Code F5 interaction and reboot behaviour
  remain to be exercised. A configured launcher is not a claim that these physical checks passed.

## Updates, backups and recovery

External tool/profile directories are the documented extension mechanism. A normal app-package update
should leave our separate project files in place. This is an expectation based on that separation, not a
guarantee of compatibility with a new app release or survival of a factory reset, reimage or failed SD card.
The [app updater](https://github.com/pollen-robotics/reachy_mini/blob/main/src/reachy_mini/apps/manager.py)
uninstalls and reinstalls the app; changes inside its installed package are therefore unsuitable.

Files surviving is only one part of working after an update. Tool APIs, selected profiles, backend settings,
service interpreter paths and dependencies must still be correct. In particular, move the companion's
dependency management away from the dashboard app environment before relying on independent updates.

- Push source commits to a private remote outside Reachy. Git on Reachy alone is not a backup.
- Back up mutable settings, personalities, memory and credentials separately; Git rollback does not undo
  an app's data-format migration. Do not commit those private backups.
- Keep everyday operation on an identified tested revision, separate from files being edited. The exact
  stable-directory switch must be reviewed after the existing robot layout has been inspected.
- Before adopting an update, record versions, back up state, test the candidate and retain a way to restore
  the previous app/dependencies, our code, service configuration and corresponding settings together.
- Record one clear start/stop procedure, startup-on-reboot behavior and log locations. Check resource use
  during real conversation so development tooling does not starve the robot.

## Documentation and permissions

This file records the current agreed development direction. Local agent notes identify the Remote SSH setup;
historical Mac-first plans and earlier runtime reports do not override it. Keep current setup status separate
from historical feature delivery claims.

Keep architecture and tool contracts in their existing docs, the backlog in `docs/roadmap.md`, and dated
validation evidence in `docs/test_summary.md`. Label historical results and outstanding hardware checks.

Get explicit approval before commands or changes, as requested by the user. Agreement on this setup is
not authorization to install packages, create a remote repository, transfer files, change services or
restart the robot. Report concrete results and limitations, with concise progress updates during work.
