# Retired patch diagnostics

Moved out of robot_tools during recovery on 2026-10-16. These source transforms are
historical evidence, not an installation or deployment mechanism. Write paths remain
unconditionally disabled and tested. Do not run them against the conversation app.
The executable Mac-specific robot_tools/deploy_runtime.py was deleted; Git history
retains it. Never restore it as the development deployment mechanism.

Only active adapters, their runtime and the component plan remain in robot_tools.
This archive is not included in the installed project packages or runtime artifacts.
