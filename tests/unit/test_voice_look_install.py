"""Check historical source validation and unconditional retirement of app patch writes."""

from pathlib import Path

import pytest

from robot_tools.install_voice_look_lifecycle import install, patch_main

SOURCE = '''def run():
    from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
    try:
        stream_manager.launch()
    except KeyboardInterrupt:
        pass
    finally:
        if own_ui_server is not None:
            own_ui_server.should_exit = True
        movement_manager.stop(reset_to_neutral=False)
'''


def test_patch_starts_before_stream_and_stops_before_movement_manager():
    source = patch_main(SOURCE)
    assert source.index("voice_look_tool.start(deps)") < source.index("stream_manager.launch()")
    assert source.index("voice_look_tool.shutdown(deps)") < source.index("movement_manager.stop(")
    assert patch_main(source) == source


def test_unknown_or_partial_app_source_is_rejected():
    with pytest.raises(ValueError, match="source changed"):
        patch_main(SOURCE.replace("stream_manager.launch()", "stream_manager.run()"))
    with pytest.raises(ValueError, match="Incomplete"):
        patch_main(patch_main(SOURCE).replace("voice_look_tool.shutdown(deps)", "pass"))


def test_check_does_not_write_or_authorise_deployment(tmp_path: Path):
    path = tmp_path / "main.py"
    path.write_text(SOURCE)
    result = install(path, None)
    assert result["changed"] and result["mode"] == "check"
    assert result["retired"] is True and result["deployment_allowed"] is False
    assert path.read_text() == SOURCE
    with pytest.raises(ValueError, match="changed since inspection"):
        install(path, None, "incorrect")


@pytest.mark.parametrize("already_patched", [False, True])
def test_install_is_retired_even_for_known_source_or_existing_backup(tmp_path: Path, already_patched: bool):
    path = tmp_path / "main.py"
    source = patch_main(SOURCE) if already_patched else SOURCE
    path.write_text(source)
    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "main.py").write_text("keep")
    with pytest.raises(RuntimeError, match="Retired"):
        install(path, backup)
    assert path.read_text() == source
    assert (backup / "main.py").read_text() == "keep"
