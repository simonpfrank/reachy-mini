"""Retired lifecycle patch installer; historical source checks only.

Installation is always refused because installed-app edits violate the no-app-edits requirement.
--check transforms source in memory only; it does not certify stock-app compatibility.
Keep this diagnostic outside the external tools directory.
"""

import argparse
import hashlib
import json
from pathlib import Path

RETIRED_REASON = (
    "Retired: direct conversation-app patches violate the no-app-edits/update-survival requirement. "
    "Installation is disabled; --check is a historical source check only."
)

MARKER = "# reachy_tools voice-look lifecycle v1"
IMPORT_OLD = "    from reachy_mini_conversation_app.tools.core_tools import ToolDependencies\n"
IMPORT_NEW = "    from reachy_mini_conversation_app.tools.core_tools import ToolDependencies, get_tools\n"
START_OLD = "    try:\n        stream_manager.launch()\n"
START_NEW = """    # reachy_tools voice-look lifecycle v1
    voice_look_tool = None
    try:
        voice_look_tool = get_tools().get("voice_look")
        if voice_look_tool is not None:
            voice_look_tool.start(deps)
        stream_manager.launch()
"""
STOP_OLD = "    finally:\n        if own_ui_server is not None:\n"
STOP_NEW = """    finally:
        if voice_look_tool is not None:
            try:
                voice_look_tool.shutdown(deps)
            except Exception:
                logger.exception("VOICE_LOOK shutdown failed")
        if own_ui_server is not None:
"""


def patch_main(source: str) -> str:
    """Validate the installed entry point and return a syntax-checked, idempotent patch."""
    if MARKER in source:
        start = START_NEW
        if "# reachy_tools phase1 v1" in source:
            beginning = source.index("        # reachy_tools phase1 v1\n")
            end = source.index("        stream_manager.launch()\n", beginning)
            speech_start = source[beginning:end]
            if "speech_tool.start(deps, stream_manager)" not in speech_start:
                raise ValueError("Incomplete speech startup integration")
            source_without_speech = source[:beginning] + source[end:]
            if all(source_without_speech.count(block) == 1 for block in (IMPORT_NEW, START_NEW, STOP_NEW)):
                compile(source, "main.py", "exec")
                return source
        if not all(source.count(block) == 1 for block in (IMPORT_NEW, start, STOP_NEW)):
            raise ValueError("Incomplete or unexpected voice-look lifecycle patch; refusing to modify main.py")
        compile(source, "main.py", "exec")
        return source
    for old, new in ((IMPORT_OLD, IMPORT_NEW), (START_OLD, START_NEW), (STOP_OLD, STOP_NEW)):
        if source.count(old) != 1:
            raise ValueError(f"Conversation app source changed; expected one occurrence of {old!r}")
        source = source.replace(old, new, 1)
    compile(source, "main.py", "exec")
    return source


def install(path: Path, backup_dir: Path | None, expected_sha256: str | None = None) -> dict[str, object]:
    """Refuse installation before filesystem access; allow historical read-only checks."""
    if backup_dir is not None:
        raise RuntimeError(RETIRED_REASON)
    original = path.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("Installed main.py changed since inspection; refusing to deploy")
    source = original.decode("utf-8")
    patched = patch_main(source)
    changed = patched != source
    return {
        "path": str(path), "changed": changed, "original_sha256": digest,
        "mode": "check", "retired": True, "deployment_allowed": False,
    }


def main() -> None:
    """Run a historical read-only check or explain why installation is retired."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-main", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--backup-dir", type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    if args.backup_dir is not None:
        parser.error(RETIRED_REASON)
    print(json.dumps(install(args.app_main, args.backup_dir, args.expected_sha256)))


if __name__ == "__main__":
    main()
