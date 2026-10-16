"""Retired Phase 1 patch installer; historical source checks only.

Installed-app edits violate the no-fork/update-survival requirement. Installation is always refused.
The remaining --check transformation is read-only and does not certify stock-app compatibility.
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

MARKER = "# reachy_tools phase1 v1"
LEGACY_START = '''        # reachy_tools phase1 v1
        speech_tool = get_tools().get("speech_control")
        if speech_tool is not None:
            speech_tool.start(deps, stream_manager)
        stream_manager.launch()
'''

PATCHES: dict[str, list[tuple[str, str]]] = {
    "main.py": [(
        "        stream_manager.launch()\n",
        '''        # reachy_tools phase1 v1
        from pathlib import Path
        from reachy_mini_conversation_app.tools.core_tools import _load_module_from_file
        speech_file = Path(config.TOOLS_DIRECTORY) / "speech_control.py"
        speech_module = _load_module_from_file("reachy_speech_runtime", speech_file)
        speech_tool = speech_module.SpeechControl()
        speech_tool.start(deps, stream_manager)
        stream_manager.launch()
''',
    )],
    "console.py": [(
        '''            return {
                "backend": HF_BACKEND,
''',
        '''            # reachy_tools phase1 v1
            speech = getattr(self.handler.deps.movement_manager, "_speech_control", None)
            return {
                "speech": speech.status() if speech is not None else None,
                "backend": HF_BACKEND,
''',
    ), (
        '''            if not self.handler._is_connected():
                raise JsonRpcError("no active session", reason="not_running")
            self.clear_audio_queue()  # barge in if mid-utterance
            await self.handler.say(text)
''',
        '''            speech = getattr(self.handler.deps.movement_manager, "_speech_control", None)
            if speech is not None and await speech.handle_text(text):
                if speech.quiet:
                    await speech.cancel_response(self.handler)
                self.handler._emit_transcript("user", text, True)
                return {"ok": True, "speech": speech.status()}
            if not self.handler._is_connected():
                raise JsonRpcError("no active session", reason="not_running")
            self.clear_audio_queue()  # barge in if mid-utterance
            await self.handler.say(text)
''',
    ), (
        '''            elif isinstance(handler_output, tuple):
                _, audio_data = handler_output
''',
        '''            elif isinstance(handler_output, tuple):
                speech = getattr(handler.deps.movement_manager, "_speech_control", None)
                if speech is not None and speech.quiet:
                    continue
                _, audio_data = handler_output
''',
    )],
    "huggingface_realtime.py": [(
        "        await self._pending_responses.put(kwargs)\n",
        '''        # reachy_tools phase1 v1
        speech = getattr(self.deps.movement_manager, "_speech_control", None)
        if speech is not None and speech.quiet:
            return
        await self._pending_responses.put(kwargs)
''',
    ), (
        '''            # Parallel tool calls enqueue duplicate empty requests; coalesce to one.
''',
        '''            speech = getattr(self.deps.movement_manager, "_speech_control", None)
            speech_generation = speech.generation if speech is not None else None
            # Parallel tool calls enqueue duplicate empty requests; coalesce to one.
''',
    ), (
        '''                self._last_response_rejected = False
                self._response_started_or_rejected_event.clear()
''',
        '''                if speech is not None and (speech.quiet or speech.generation != speech_generation):
                    break
                self._last_response_rejected = False
                self._response_started_or_rejected_event.clear()
''',
    ), (
        '''        if not text:
            raise ValueError("say: empty text")
        if not self.connection:
''',
        '''        if not text:
            raise ValueError("say: empty text")
        speech = getattr(self.deps.movement_manager, "_speech_control", None)
        if speech is not None and await speech.handle_text(text):
            if speech.quiet:
                await speech.cancel_response(self)
            self._emit_transcript("user", text, True)
            return
        if not self.connection:
''',
    ), (
        '''                async for event in self.connection:
                    logger.debug("Realtime event: %s", event.type)
''',
        '''                async for event in self.connection:
                    speech = getattr(self.deps.movement_manager, "_speech_control", None)
                    if speech is not None and await speech.on_event(event, self):
                        continue
                    logger.debug("Realtime event: %s", event.type)
''',
    )],
    "tools/core_tools.py": [(
        '''    tool = get_tools().get(tool_name)
    if not tool:
''',
        '''    # reachy_tools phase1 v1
    speech = getattr(deps.movement_manager, "_speech_control", None)
    if speech is not None and speech.quiet:
        return {"status": "quiet", "executed": False}
    tool = get_tools().get(tool_name)
    if not tool:
''',
    )],
    "moves.py": [(
        "    def clear_move_queue(self) -> None:\n",
        '''    # reachy_tools phase1 v1
    def set_voice_facing(self, heading: float | None, body: float = 0.0) -> None:
        """Retain the speaker-facing idle anchor through the worker's command queue."""
        self._command_queue.put(("voice_facing", None if heading is None else (heading, body)))

    def clear_move_queue(self) -> None:
''',
    ), (
        '''        elif command == "clear_queue":
''',
        '''        elif command == "voice_facing":
            self._voice_facing = payload
        elif command == "clear_queue":
''',
    ), (
        '''        elif command == "set_speaking":
            if not self._head_tracking:
                return
            speaking = bool(payload)
            if self._is_speaking == speaking:
                return
            self._is_speaking = speaking
''',
        '''        elif command == "set_speaking":
            speaking = bool(payload)
            if self._is_speaking == speaking:
                return
            self._is_speaking = speaking
            if not self._head_tracking:
                return
''',
    ), (
        '''                    breathing_move = BreathingMove(
                        interpolation_start_pose=current_head_pose,
                        interpolation_start_antennas=current_antennas,
                        interpolation_duration=1.0,
                    )
''',
        '''                    factory = getattr(self, "_voice_look_idle_factory", None)
                    facing = getattr(self, "_voice_facing", None)
                    if factory is not None and facing is not None:
                        breathing_move = factory(current_head_pose, current_antennas, facing)
                    else:
                        breathing_move = BreathingMove(
                            interpolation_start_pose=current_head_pose,
                            interpolation_start_antennas=current_antennas,
                            interpolation_duration=1.0,
                        )
''',
    ), (
        '''            "queue_size": len(self.move_queue),
''',
        '''            "queue_size": len(self.move_queue),
            "is_speaking": self._is_speaking,
            "primary_is_idle": self.state.current_move is None or isinstance(self.state.current_move, BreathingMove),
            "primary_settling": bool(
                isinstance(self.state.current_move, BreathingMove)
                and self.state.move_start_time is not None
                and self._now() - self.state.move_start_time < self.state.current_move.interpolation_duration
            ),
            "voice_facing": getattr(self, "_voice_facing", None),
''',
    )],
}


def patch_source(name: str, source: str) -> str:
    """Apply only exact known source fragments, or verify all installed fragments on a repeat run."""
    patches = list(PATCHES[name])
    # App 1.1 keeps its new asynchronous interrupt/epoch playback behavior.
    if name == "console.py" and "sample_rate, audio_data = handler_output" in source:
        old, new = patches[1]
        patches[1] = (
            old.replace("self.clear_audio_queue()  # barge in if mid-utterance", "await self.handler.interrupt()"),
            new.replace("self.clear_audio_queue()  # barge in if mid-utterance", "await self.handler.interrupt()"),
        )
        old, new = patches[2]
        patches[2] = (old.replace("_, audio_data = handler_output", "sample_rate, audio_data = handler_output"),
                      new.replace("_, audio_data = handler_output", "sample_rate, audio_data = handler_output"))
        patches.extend([
            ('''                            self._stop_event.is_set()
''', '''                            (speech is not None and speech.quiet)
                            or self._stop_event.is_set()
'''),
            ('''                    if handler is not self.handler or playback_epoch != handler.playback_epoch:
''', '''                    if (
                        (speech is not None and speech.quiet)
                        or handler is not self.handler or playback_epoch != handler.playback_epoch
                    ):
'''),
        ])
    if name == "main.py" and LEGACY_START in source:
        source = source.replace(LEGACY_START, patches[0][1])
    # Migrate the original synchronous quiet input hooks if rechecking an earlier install.
    source = source.replace("and speech.handle_text(text):", "and await speech.handle_text(text):")
    if MARKER in source:
        if not all(new in source for _, new in patches):
            raise ValueError(f"Partial or incompatible Phase 1 patch in {name}")
    else:
        for old, new in patches:
            if source.count(old) != 1:
                raise ValueError(f"Unexpected {name}: expected one occurrence of {old[:80]!r}")
            source = source.replace(old, new, 1)
    compile(source, name, "exec")
    return source


def install(app_dir: Path, backup_dir: Path | None) -> dict[str, object]:
    """Refuse installation before filesystem access; allow historical read-only checks."""
    if backup_dir is not None:
        raise RuntimeError(RETIRED_REASON)
    original = {name: (app_dir / name).read_bytes() for name in PATCHES}
    patched = {name: patch_source(name, data.decode()) for name, data in original.items()}
    changed = [name for name, source in patched.items() if source.encode() != original[name]]
    return {
        "mode": "check", "retired": True, "deployment_allowed": False, "changed": changed,
        "sha256": {name: hashlib.sha256(source.encode()).hexdigest() for name, source in patched.items()},
    }


def main() -> None:
    """Run a historical read-only check or explain why installation is retired."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    if args.backup_dir is not None:
        parser.error(RETIRED_REASON)
    print(json.dumps(install(args.app_dir, args.backup_dir)))


if __name__ == "__main__":
    main()
