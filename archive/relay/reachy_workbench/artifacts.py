"""Bind release artifacts to checked source, using an explicit production-file allowlist."""

import hashlib
import json
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

RUNTIME_FILES = (
    "robot_tools/__init__.py",
    "robot_tools/conversation_runtime.py",
    "robot_tools/voice_look.py",
    "robot_tools/speech_control.py",
    "robot_tools/location.py",
    "robot_tools/today.py",
)
ENTRYPOINT = "from robot_tools.conversation_runtime import main\nif __name__ == '__main__':\n    main()\n"


def checked_sources(root: Path) -> dict[str, str]:
    """Fingerprint production, workbench and test inputs without reading secrets or live state."""
    files = {root / name for name in RUNTIME_FILES}
    files.add(root / "pyproject.toml")
    if (root / "uv.lock").exists():
        files.add(root / "uv.lock")
    for directory in ("reachy_workbench", "reachy_hub", "tests/unit", "tests/data"):
        files.update(
            path for path in (root / directory).rglob("*") if path.is_file() and "__pycache__" not in path.parts
        )
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}


def receipt_path(root: Path) -> Path:
    """Keep local check evidence separate from source, secrets and robot configuration."""
    return root / ".workbench" / "check.json"


def save_receipt(root: Path, sources: dict[str, str], phases: list[str], scope: str) -> Path:
    """Write successful check evidence only after every requested phase passes."""
    path = receipt_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"status": "passed", "scope": scope, "phases": phases, "sources": sources}, indent=2) + "\n"
    )
    return path


def build(root: Path, output_dir: Path) -> Path:
    """Build exactly the checked code; reject missing/stale evidence and exclude development helpers."""
    receipt = receipt_path(root)
    if not receipt.exists():
        raise ValueError("No successful check receipt. Run reachy check before building.")
    evidence = json.loads(receipt.read_text())
    sources = checked_sources(root)
    if evidence.get("status") != "passed" or evidence.get("sources") != sources:
        raise ValueError("Source has changed since the successful check. Run reachy check again.")
    files = {name: (root / name).read_bytes() for name in RUNTIME_FILES}
    files["__main__.py"] = ENTRYPOINT.encode()
    manifest = {
        "schema": 1,
        "purpose": "external runtime and ordinary tool adapters; no installed-app patches",
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        "check": evidence,
        "deployment": "not performed; inspect and review a separate installer plan before applying",
    }
    files["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    content = buffer.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact = output_dir / f"reachy-runtime-{digest[:16]}.pyz"
    if artifact.exists() and artifact.read_bytes() != content:
        raise ValueError("An existing artifact with this identity differs; refusing to overwrite it.")
    artifact.write_bytes(content)
    return artifact


def inspect(artifact: Path) -> dict[str, Any]:
    """Validate archive members and hashes before displaying its release evidence."""
    with zipfile.ZipFile(artifact) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        expected = set(RUNTIME_FILES) | {"__main__.py"}
        if set(manifest["files"]) != expected or set(archive.namelist()) != expected | {"manifest.json"}:
            raise ValueError("Artifact contains an unexpected file set.")
        for name, digest in manifest["files"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f"Artifact hash mismatch: {name}")
    return manifest
