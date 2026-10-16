# Remote development setup (2026-10-16)

Simon approved making the documented Remote SSH setup operational, then explaining how to open it.
Keep the existing app, tools, runtime service and everyday settings intact. Create the development copy at
`/home/pollen/projects/reachy-tools`, preserving existing Git history and all reviewed source changes.
Record a local backup before transfer. No public repository or account creation is authorised.

Use a separate Python environment with the robot's actual SDK/app source revision, saved external-tool/profile
paths and separate instance/state directories. Development relay ports are 8786/8787; everyday ports stay
8766/8767. Make the two tool adapters accept an optional loopback control port, retaining the existing default.
Provide ordinary VS Code launches for the actual app, companion runtime and hub, plus unit-test discovery.
Verify source hashes, real app tool loading, isolated relay health, unit tests and Git status without starting
hardware conversation or restarting the working app. Report any dependency/storage or remote-backup limits.

Answers: Wireless robot, Mac VS Code client, Python/uv, existing live configuration retained. Latest approval
supersedes the historical Mac-only workflow below and authorises the necessary setup and verification commands.

# Historical development workflow repair

## Request and boundaries

Simon requires a visible, documented development process: normal Python entry points, code runnable/debuggable
on the Mac, repeatable tests before deployment, and explicit evidence instead of guessing on the robot.
The latest request supersedes further feature repair/deployment work. Leave the current robot runtime alone.
Preserve all existing uncommitted work.

## First deliverable: working local development

1. Add a normal packaged reachy command and python -m reachy_workbench fallback.
2. dev runs the real speech relay against clearly labelled local fake app/provider peers. Interactive text
   exercises quiet/resume; simulated transcripts exercise the spoken-command parser. No robot/cloud/token use.
3. check runs lint, the maintained unit/transport tests, and an executable offline scenario. Record exact
   checked source hashes. Report excluded experimental tracker tests explicitly; --all includes them.
4. build requires a matching successful check receipt and produces an inspectable zip application/manifest.
   Ship only runtime/tool/package files, no deployment helpers, fakes, secrets or state.
5. status --robot HOST reads daemon/app status. Optional SSH reads loopback runtime health with a simple
   fixed curl command, no embedded Python/Bash program and no mutations.
6. Add VS Code launch/test configurations and a short README with one setup step and everyday commands.
7. Document deployment as a separate next deliverable: normal testable installer module, explicit target/profile,
   reviewed artifact, health/acceptance gates and rollback. Do not wrap or run the existing embedded deploy script.

## Working agreement

Before changes, state the goal, files/systems affected and verification. During work, report concrete progress
and decisions at least every 60 seconds; use more frequent updates when a command fails or scope changes.
Read relevant local guidance first. Distinguish offline, upstream compatibility and hardware acceptance.
No feature is fixed because it was disabled. No robot deployment without a concrete reviewed change.

## Answer fields

- Robot: existing Wireless, unchanged.
- Development machine/environment: existing Mac and uv/.venv, no second environment/resource clone.
- Interface: CLI plus existing VS Code debugger; no new web app/framework.
- Physical robot changes in this deliverable: none.
- Full deployment implementation: review the documented approach after the local workflow is runnable.
