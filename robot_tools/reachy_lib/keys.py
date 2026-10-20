"""API keys for the tools, the same call on every platform. Standard library only.

A key comes from, in order:
1. an environment variable, ``<NAME>_API_KEY`` (works anywhere: the sim's ``~/.env``, tests);
2. the platform's own encrypted store: ``systemd-creds`` files on Linux (the robot), the login Keychain on macOS
   (via ``/usr/bin/security``), Credential Manager on Windows (via ``ctypes``; not yet tested on Windows).

Keys are never in source, prompts, arguments or messages.

Manage keys with the command (``scripts/keys.sh`` and ``scripts/keys.bat`` call it)::

    python robot_tools/reachy_lib/keys.py add|remove|check NAME
    python robot_tools/reachy_lib/keys.py list          (robot only)
"""

import getpass
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SYSTEMD_CREDS = "/usr/bin/systemd-creds"
SECURITY = "/usr/bin/security"
TIMEOUT_S = 10
KEYCHAIN_NOT_FOUND = 44  # exit status of `security` when there is no such item
ERROR_NOT_FOUND = 1168  # Windows: no such credential
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
NAME = re.compile(r"[a-z0-9_]+")
SAFE_KEYCHAIN_VALUE = re.compile(r"[A-Za-z0-9._~+/=:-]+")  # the Keychain command is built from text: allow no quoting
SAFE_SERVICE = re.compile(r"[A-Za-z0-9._-]+")
USAGE = "Usage: keys.py add NAME | remove NAME | check NAME | list"


class KeyNotSet(RuntimeError):
    """No key of that name is stored anywhere the tools look."""


class ListNotSupported(RuntimeError):
    """This platform's store cannot list the keys in it."""


def keys_dir() -> Path:
    """Where the systemd-encrypted key files live (the robot)."""
    return Path(os.environ.get("REACHY_TOOLS_KEYS_DIR", "~/.config/reachy_tools/keys")).expanduser()


def keychain_service() -> str:
    """The Keychain / Credential Manager service the keys are filed under; tests set another one."""
    return os.environ.get("REACHY_TOOLS_KEYCHAIN_SERVICE", "reachy-tools")


def store_kind() -> str:
    """``keychain`` on macOS, ``windows`` on Windows, ``systemd`` everywhere else (the robot)."""
    if sys.platform == "darwin":
        return "keychain"
    return "windows" if sys.platform == "win32" else "systemd"


def env_name(name: str) -> str:
    """The environment variable that overrides the stored key, e.g. ``tavily`` -> ``TAVILY_API_KEY``."""
    return f"{name.upper().replace('-', '_')}_API_KEY"


def _target(name: str) -> str:
    return f"{keychain_service()}/{name}"


def get_key(name: str) -> str:
    """The key called ``name``: the environment variable if set, otherwise the platform's store.

    Args:
        name: Key name, lower case (e.g. ``tavily``).

    Returns:
        The key.

    Raises:
        KeyNotSet: No such key is stored.
        RuntimeError: A key is stored but could not be read; the message never contains the key.
    """
    from_environment = os.environ.get(env_name(name), "").strip()
    return from_environment or stored_key(name)


def stored_key(name: str) -> str:
    """The key from the platform's store only, ignoring the environment (see ``get_key``)."""
    kind = store_kind()
    if kind == "keychain":
        return _read_keychain(name)
    if kind == "windows":
        return _read_windows(name)
    return _read_systemd(name)


def set_key(name: str, key: str) -> None:
    """Store ``key`` in the platform's store, replacing any existing one.

    Raises:
        ValueError: The name is not lower-case letters, digits or ``_``, or the Keychain cannot take the key safely.
        RuntimeError: The store refused it.
    """
    _check_name(name)
    kind = store_kind()
    if kind == "keychain":
        _write_keychain(name, key)
    elif kind == "windows":
        _cred_write(_target(name), key)
    else:
        _write_systemd(name, key)


def delete_key(name: str) -> None:
    """Remove the key from the platform's store.

    Raises:
        KeyNotSet: There was no such key.
    """
    _check_name(name)
    kind = store_kind()
    if kind == "keychain":
        argv = [SECURITY, "delete-generic-password", "-s", keychain_service(), "-a", name]
        if _run(name, argv).returncode != 0:
            raise KeyNotSet(f"No {name} key is stored")
    elif kind == "windows":
        if not _cred_delete(_target(name)):
            raise KeyNotSet(f"No {name} key is stored")
    else:
        path = keys_dir() / f"{name}.cred"
        if not path.exists():
            raise KeyNotSet(f"No {name} key is stored")
        path.unlink()


def stored_names() -> list[str]:
    """Names of the stored keys (the robot only).

    Raises:
        ListNotSupported: On macOS and Windows.
    """
    kind = store_kind()
    if kind != "systemd":
        store = {"keychain": "the macOS Keychain", "windows": "Windows Credential Manager"}[kind]
        raise ListNotSupported(f"Listing is not available with {store}; use: scripts/keys.sh check NAME")
    directory = keys_dir()
    return sorted(path.stem for path in directory.glob("*.cred")) if directory.is_dir() else []


def _check_name(name: str) -> None:
    if not NAME.fullmatch(name):
        raise ValueError("A key name is lower-case letters, digits or _ (e.g. tavily)")


def _run(name: str, argv: list[str], stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(  # noqa: S603 -- fixed commands, never a shell
            argv, input=stdin, capture_output=True, timeout=TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"The {name} key could not be read ({type(error).__name__})") from error


def _value(name: str, result: subprocess.CompletedProcess[bytes]) -> str:
    key = result.stdout.decode().strip() if result.returncode == 0 else ""
    if not key:
        raise RuntimeError(f"The {name} key could not be decrypted (scripts/keys.sh check {name})")
    return key


def _read_systemd(name: str) -> str:
    path = keys_dir() / f"{name}.cred"
    if not path.exists():
        raise KeyNotSet(f"No {name} key is stored")
    return _value(name, _run(name, [SYSTEMD_CREDS, "--user", f"--name={name}", "decrypt", str(path), "-"]))


def _write_systemd(name: str, key: str) -> None:
    directory = keys_dir()
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    temporary = directory / f".{name}.cred.new"
    result = _run(name, [SYSTEMD_CREDS, "--user", "encrypt", f"--name={name}", "-", str(temporary)], key.encode())
    if result.returncode != 0:
        raise RuntimeError(f"The {name} key could not be encrypted")
    temporary.chmod(0o600)
    temporary.replace(directory / f"{name}.cred")


def _read_keychain(name: str) -> str:
    result = _run(name, [SECURITY, "find-generic-password", "-s", keychain_service(), "-a", name, "-w"])
    if result.returncode == KEYCHAIN_NOT_FOUND:
        raise KeyNotSet(f"No {name} key is stored")
    return _value(name, result)


def _write_keychain(name: str, key: str) -> None:
    service = keychain_service()
    if not SAFE_KEYCHAIN_VALUE.fullmatch(key):
        raise ValueError("The Keychain can only take a key made of letters, digits and . _ ~ + / = : -")
    if not SAFE_SERVICE.fullmatch(service):
        raise ValueError("REACHY_TOOLS_KEYCHAIN_SERVICE may only use letters, digits and . _ -")
    # `security -i` reads its command from stdin, so the key never appears in a process list
    command = f'add-generic-password -U -s "{service}" -a "{name}" -w "{key}"\n'
    if _run(name, [SECURITY, "-i"], command.encode()).returncode != 0:
        raise RuntimeError(f"The {name} key could not be stored in the Keychain")


def _read_windows(name: str) -> str:
    try:
        blob = _cred_read(_target(name))
    except OSError as error:
        raise RuntimeError(f"The {name} key could not be read ({type(error).__name__})") from error
    if blob is None:
        raise KeyNotSet(f"No {name} key is stored")
    key = blob.decode("utf-16-le").strip()
    if not key:
        raise RuntimeError(f"The {name} key could not be decrypted (scripts/keys.bat check {name})")
    return key


def _credential_api() -> tuple[Any, Any]:
    """advapi32 with typed signatures, and the CREDENTIALW structure. Windows only; NOT YET TESTED on Windows."""
    import ctypes
    from ctypes import wintypes

    class Credential(ctypes.Structure):
        _fields_ = [  # noqa: RUF012 -- ctypes layout
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
    pointer = ctypes.POINTER(Credential)
    advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(pointer)]
    advapi.CredReadW.restype = wintypes.BOOL
    advapi.CredWriteW.argtypes = [pointer, wintypes.DWORD]
    advapi.CredWriteW.restype = wintypes.BOOL
    advapi.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    advapi.CredDeleteW.restype = wintypes.BOOL
    advapi.CredFree.argtypes = [ctypes.c_void_p]
    advapi.CredFree.restype = None
    return advapi, Credential


def _cred_read(target: str) -> bytes | None:
    """The credential's secret bytes, or None if there is none. Windows only; NOT YET TESTED on Windows."""
    import ctypes

    advapi, credential = _credential_api()
    found = ctypes.POINTER(credential)()
    if not advapi.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(found)):
        error = ctypes.get_last_error()  # type: ignore[attr-defined,unused-ignore]
        if error == ERROR_NOT_FOUND:
            return None
        raise OSError(error, "CredReadW failed")
    try:
        return ctypes.string_at(found.contents.CredentialBlob, found.contents.CredentialBlobSize)
    finally:
        advapi.CredFree(found)


def _cred_write(target: str, key: str) -> None:
    """Store the key as a generic credential (UTF-16, as Credential Manager shows it). NOT YET TESTED on Windows."""
    import ctypes

    advapi, credential = _credential_api()
    blob = key.encode("utf-16-le")
    buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    entry = credential()
    entry.Type = CRED_TYPE_GENERIC
    entry.TargetName = target
    entry.CredentialBlobSize = len(blob)
    entry.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    entry.Persist = CRED_PERSIST_LOCAL_MACHINE
    entry.UserName = "reachy-tools"
    if not advapi.CredWriteW(ctypes.byref(entry), 0):
        raise OSError(ctypes.get_last_error(), "CredWriteW failed")  # type: ignore[attr-defined,unused-ignore]


def _cred_delete(target: str) -> bool:
    """Delete the credential; False if there was none. Windows only; NOT YET TESTED on Windows."""
    import ctypes

    advapi, _ = _credential_api()
    if advapi.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
        return True
    error = ctypes.get_last_error()  # type: ignore[attr-defined,unused-ignore]
    if error == ERROR_NOT_FOUND:
        return False
    raise OSError(error, "CredDeleteW failed")


def _check(name: str) -> int:
    try:
        stored_key(name)
    except RuntimeError:
        problem = f"Problem: the {name} key is missing or cannot be decrypted. Run: scripts/keys.sh add {name}"
        print(problem, file=sys.stderr)
        return 1
    print(f"OK: the {name} key is stored and decrypts.")
    return 0


def _add(name: str) -> int:
    prompt = f"Paste the {name} key, then press Enter (it will not show): "
    key = (getpass.getpass(prompt) if sys.stdin.isatty() else sys.stdin.readline()).strip()
    if not key:
        print("No key entered; nothing stored.", file=sys.stderr)
        return 1
    set_key(name, key)
    return _check(name)


def _remove(name: str) -> int:
    try:
        delete_key(name)
    except KeyNotSet:
        print(f"No {name} key is stored.", file=sys.stderr)
        return 1
    print(f"Removed the {name} key.")
    return 0


def _list() -> int:
    try:
        names = stored_names()
    except ListNotSupported as error:
        print(error, file=sys.stderr)
        return 1
    print("\n".join(names) or "No keys stored.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the key command; returns the process exit status (0 done, 1 failed, 2 bad arguments)."""
    args = sys.argv[1:] if argv is None else argv
    command, name = (args + ["", ""])[:2]
    if command not in ("add", "remove", "check", "list"):
        print(USAGE, file=sys.stderr)
        return 2
    if command != "list" and not NAME.fullmatch(name):
        print("Give a key name: lower-case letters, digits or _ (e.g. tavily).", file=sys.stderr)
        return 2
    try:
        if command == "list":
            return _list()
        return {"add": _add, "remove": _remove, "check": _check}[command](name)
    except (RuntimeError, ValueError, OSError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
