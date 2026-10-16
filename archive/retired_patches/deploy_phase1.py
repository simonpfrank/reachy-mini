"""Retired Phase 1 deployment entry point.

The original deployment patched the installed conversation app and wrote app-local profiles/settings.
That violates the no-app-edits/update-survival requirement. It must never run again.
This replacement performs no filesystem writes, daemon calls or app restarts.
Previously staged copies on the robot have not been changed and must not be executed.
"""

RETIRED_REASON = (
    "Retired: Phase 1 deployment modifies the installed conversation app. "
    "The no-app-edits/update-survival requirement prohibits this deployment. "
    "No robot calls or file changes were made."
)


def main() -> None:
    """Refuse the retired deployment unconditionally, before any side effects."""
    raise SystemExit(RETIRED_REASON)


if __name__ == "__main__":
    main()
