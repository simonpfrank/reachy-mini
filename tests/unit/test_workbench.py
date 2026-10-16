"""Check the public local-workbench commands and release/evidence boundaries."""

import subprocess
import sys
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from reachy_workbench import artifacts
from reachy_workbench.cli import main
from reachy_workbench.lab import Lab, demo

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_offline_demo_runs_production_transport_without_cloud(tmp_path, monkeypatch):
    from robot_tools.conversation_runtime import Runtime

    monkeypatch.setattr(Runtime, "allocate", Mock(side_effect=AssertionError("Must not allocate a cloud session")))
    messages = []
    results = await demo(tmp_path / "speech.json", messages.append)
    assert len(results) == 6
    assert len(messages) == 6
    assert all(message.startswith("PASS ") for message in messages)


@pytest.mark.asyncio
async def test_simulated_voice_quiet_and_restart_are_visible_without_fake_hardware_claims(tmp_path):
    async with Lab(tmp_path / "speech.json") as lab:
        await lab.transcript("shut up")
        assert lab.runtime.state.status()["quiet"]
        assert (await lab.turn("dance")) == {"quiet": True, "audio_markers": 0, "actions": 0}
        await lab.restart()
        assert lab.runtime.state.status()["quiet"]
        await lab.transcript("you can speak again")
        result = await lab.turn("hello")
        assert result["audio_markers"] == 1 and not result["quiet"]
        assert lab.interrupts >= 2
        assert not lab.runtime.state.status()["voice_running"]


def make_project(tmp_path):
    for name in artifacts.RUNTIME_FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('"""Sample release source."""\n')
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')
    return tmp_path


def test_artifact_rejects_unchecked_and_changed_source(tmp_path):
    root = make_project(tmp_path)
    with pytest.raises(ValueError, match="Run reachy check"):
        artifacts.build(root, root / "dist")
    artifacts.save_receipt(root, artifacts.checked_sources(root), ["test"], "maintained")
    (root / "robot_tools/location.py").write_text("CHANGED = True\n")
    with pytest.raises(ValueError, match="changed"):
        artifacts.build(root, root / "dist")


def test_release_is_deterministic_and_excludes_secrets_fakes_and_deploy_helpers(tmp_path):
    root = make_project(tmp_path)
    (root / ".env").write_text("SECRET=must-not-ship")
    (root / "robot_tools/deploy_runtime.py").write_text("must_not_ship = True\n")
    (root / "robot_tools/dev_fake.py").write_text("must_not_ship = True\n")
    artifacts.save_receipt(root, artifacts.checked_sources(root), ["offline tests"], "maintained")
    first = artifacts.build(root, root / "out")
    second = artifacts.build(root, root / "out")
    assert first == second
    manifest = artifacts.inspect(first)
    assert manifest["check"]["status"] == "passed"
    with zipfile.ZipFile(first) as archive:
        assert set(archive.namelist()) == set(artifacts.RUNTIME_FILES) | {"__main__.py", "manifest.json"}
        assert b"must-not-ship" not in b"".join(archive.read(name) for name in archive.namelist())


def test_artifact_rejects_tampering(tmp_path):
    root = make_project(tmp_path)
    artifacts.save_receipt(root, artifacts.checked_sources(root), ["test"], "maintained")
    artifact = artifacts.build(root, root / "out")
    with zipfile.ZipFile(artifact) as original:
        content = {name: original.read(name) for name in original.namelist()}
    content["robot_tools/location.py"] = b"tampered = True\n"
    with zipfile.ZipFile(artifact, "w") as changed:
        for name, data in content.items():
            changed.writestr(name, data)
    with pytest.raises(ValueError, match="hash mismatch"):
        artifacts.inspect(artifact)


def test_no_deploy_command_can_silently_invoke_old_remote_script():
    with pytest.raises(SystemExit) as result:
        main(["deploy"])
    assert result.value.code != 0


def test_public_module_help_has_normal_commands_and_no_side_effects():
    result = subprocess.run(  # noqa: S603 -- fixed local module, no shell or network
        [sys.executable, "-m", "reachy_workbench", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    for name in ("dev", "demo", "check", "status", "build", "runtime"):
        assert name in result.stdout
