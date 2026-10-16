"""Normal Python commands for local development, verification, status and packaging."""

import argparse
import asyncio
import json
import logging
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx
from websockets.asyncio.client import connect

from reachy_workbench import artifacts
from reachy_workbench.lab import Lab, demo


def parser() -> argparse.ArgumentParser:
    """Describe commands without importing hardware tools or reading robot configuration."""
    result = argparse.ArgumentParser(prog="reachy", description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    dev = commands.add_parser("dev", help="interactive OFFLINE relay workbench; no robot/cloud")
    dev.add_argument("--state-dir", type=Path, default=Path(".workbench/dev"))
    commands.add_parser("demo", help="run the repeatable offline transport scenario")
    check = commands.add_parser("check", help="lint, maintained tests and offline scenario")
    check.add_argument("--all", action="store_true", help="include the separate experimental tracker suite")
    runtime = commands.add_parser("runtime", help="run production runtime in foreground using an explicit config")
    runtime.add_argument("--config", type=Path, required=True)
    status = commands.add_parser("status", help="read robot/app status without changing anything")
    status.add_argument("--robot", required=True, help="robot host or IP, without a URL scheme")
    status.add_argument("--ssh", help="optional SSH target to read loopback runtime health")
    status.add_argument("--identity", type=Path, help="optional existing SSH identity file")
    bundle = commands.add_parser("build", help="package checked source; does not deploy")
    bundle.add_argument("--output", type=Path, default=Path(".workbench/releases"))
    inspect = commands.add_parser("inspect", help="validate/show an artifact manifest without executing it")
    inspect.add_argument("artifact", type=Path)
    return result


def project_root() -> Path:
    """Locate the checked-out project for source checks/builds, failing clearly outside it."""
    for root in (Path.cwd(), *Path.cwd().parents):
        if (root / "pyproject.toml").exists() and (root / "robot_tools/conversation_runtime.py").exists():
            return root
    raise ValueError("Run check/build from this repository. dev/runtime/status also work as installed commands.")


async def console(state_dir: Path) -> None:
    """Run an interactive lab in a terminal where breakpoints and events remain visible."""
    print("OFFLINE SIMULATION: real relay, fake app/provider; no robot, cloud, STT/TTS or motor output.", flush=True)
    print("Commands: text request | voice <simulated transcript> | status | restart | quit", flush=True)
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    transport, _ = await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, sys.stdin)
    try:
        async with Lab(state_dir.resolve() / "speech.json") as lab:
            while True:
                print("reachy> ", end="", flush=True)
                line = await reader.readline()
                if not line or line.decode().strip() in {"quit", "exit"}:
                    return
                text = line.decode().strip()
                if text == "status":
                    print(json.dumps(lab.runtime.state.status(), indent=2), flush=True)
                elif text == "restart":
                    await lab.restart()
                    print("Local runtime restarted; state reloaded.", flush=True)
                elif text.startswith("voice "):
                    status = await lab.transcript(text[6:])
                    print(f"Simulated transcript handled; quiet={status['quiet']}", flush=True)
                elif text:
                    print(json.dumps(await lab.turn(text)), flush=True)
    finally:
        transport.close()


def run_demo() -> list[str]:
    """Exercise the real relay with isolated temporary state and explicit limitations."""
    print("OFFLINE transport checks: no robot/cloud; audio markers are not audible playback.", flush=True)
    with tempfile.TemporaryDirectory(prefix="reachy-workbench-") as directory:
        return asyncio.run(demo(Path(directory) / "speech.json"))


def check(root: Path, include_experimental: bool) -> int:
    """Run bounded named phases and tie successful evidence to unchanged source."""
    before = artifacts.checked_sources(root)
    receipt = artifacts.receipt_path(root)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"status": "running", "sources": before}) + "\n")
    phases: list[str] = []
    commands = [
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "reachy_workbench",
            *artifacts.RUNTIME_FILES,
            "tests/unit/test_workbench.py",
        ],
        [sys.executable, "-m", "pytest", "-q", "tests/unit"],
    ]
    if not include_experimental:
        print(
            "Scope: maintained unit/transport tests. Experimental test_tracker.py excluded; --all includes it.",
            flush=True,
        )
        commands[1].append("--ignore=tests/unit/test_tracker.py")
    for name, command in zip(("lint", "unit/transport tests"), commands, strict=True):
        print(f"RUN {name}: {shlex.join(command)}", flush=True)
        result = subprocess.run(command, cwd=root, check=False)  # noqa: S603 -- fixed local Python tools
        if result.returncode:
            print(f"FAIL {name}; no new passing receipt written.", flush=True)
            return result.returncode
        phases.append(name)
    run_demo()
    phases.append("offline transport scenario")
    if artifacts.checked_sources(root) != before:
        raise ValueError("Source changed during checks; no passing receipt written. Rerun against stable source.")
    receipt = artifacts.save_receipt(root, before, phases, "all" if include_experimental else "maintained")
    print(f"PASS check evidence: {receipt}", flush=True)
    return 0


async def rpc_status(host: str) -> dict[str, Any]:
    """Read one app status reply without triggering speech, tools or a restart."""
    async with connect(f"ws://{host}:7860/rpc", open_timeout=3, close_timeout=1) as ws:
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": "status", "method": "conversation.status", "params": {}}))
        async with asyncio.timeout(4):
            while True:
                reply = json.loads(await ws.recv())
                if reply.get("id") == "status":
                    if "error" in reply:
                        raise ValueError("App status RPC was rejected")
                    return {
                        key: reply["result"].get(key)
                        for key in (
                            "personality",
                            "voice",
                            "language",
                            "backend_connected",
                            "backend_connection_state",
                        )
                    }


async def status(args: argparse.Namespace) -> int:
    """Report only operational status; do not echo credentials or conversation content."""
    host = args.robot
    if any(value in host for value in ("/", "?", "#", "@", ":")) or not host.strip():
        raise ValueError("--robot requires a host/IP without scheme, path or credentials")
    failed = False
    async with httpx.AsyncClient(timeout=4, trust_env=False) as client:
        try:
            response = await client.get(f"http://{host}:8000/api/apps/current-app-status")
            response.raise_for_status()
            body = response.json()
            print(json.dumps({"robot": host, "app_state": body.get("state")}, indent=2), flush=True)
        except (httpx.HTTPError, ValueError) as error:
            failed = True
            print(f"Daemon status unavailable: {type(error).__name__}", flush=True)
    try:
        print(json.dumps({"conversation": await rpc_status(host)}, indent=2), flush=True)
    except Exception as error:
        failed = True
        print(f"App status unavailable: {type(error).__name__}", flush=True)
    if args.ssh:
        command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4"]
        if args.identity:
            command.extend(["-i", str(args.identity.expanduser())])
        command.extend([args.ssh, "curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8767/state"])
        result = await asyncio.to_thread(
            subprocess.run,
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode:
            failed = True
            print("Loopback runtime status unavailable over SSH.", flush=True)
        else:
            print(json.dumps({"runtime": json.loads(result.stdout)}, indent=2), flush=True)
    return int(failed)


def main(argv: list[str] | None = None) -> int:
    """Run a normal command, exposing errors in the terminal without silently mutating a robot."""
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        if args.command == "dev":
            asyncio.run(console(args.state_dir))
        elif args.command == "demo":
            run_demo()
        elif args.command == "check":
            return check(project_root(), args.all)
        elif args.command == "runtime":
            from robot_tools.conversation_runtime import Runtime, State

            config = json.loads(args.config.read_text())
            asyncio.run(Runtime(State(Path(config["speech_state"]).expanduser()), config).run())
        elif args.command == "status":
            return asyncio.run(status(args))
        elif args.command == "build":
            print(artifacts.build(project_root(), args.output.resolve()), flush=True)
        elif args.command == "inspect":
            print(json.dumps(artifacts.inspect(args.artifact), indent=2), flush=True)
        return 0
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
        return 130
    except Exception as error:
        print(f"ERROR {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        return 1
