"""reachy_lib.keys: one key lookup for every platform: environment variable, then the platform's encrypted store."""

import io
import subprocess
import sys
import types
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "robot_tools"
DUMMY = "s3cret-value"


@pytest.fixture
def keys(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(TOOLS))
    sys.modules.pop("reachy_lib.keys", None)
    from reachy_lib import keys as module

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("REACHY_TOOLS_KEYCHAIN_SERVICE", raising=False)
    monkeypatch.setenv("REACHY_TOOLS_KEYS_DIR", str(tmp_path / "keys"))
    runs: list[list[str]] = []
    inputs: list[bytes | None] = []
    reply = {"returncode": 0, "stdout": (DUMMY + "\n").encode()}

    def run(argv, **kwargs):
        runs.append(argv)
        inputs.append(kwargs.get("input"))
        if "encrypt" in argv:  # systemd-creds writes the file named last
            Path(argv[-1]).write_bytes(b"encrypted")
        return subprocess.CompletedProcess(argv, reply["returncode"], reply["stdout"], b"")

    monkeypatch.setattr(module.subprocess, "run", run)
    return types.SimpleNamespace(
        module=module, runs=runs, inputs=inputs, reply=reply, dir=tmp_path / "keys", mp=monkeypatch
    )


def use(keys, kind: str):
    keys.mp.setattr(keys.module, "store_kind", lambda: kind)


def stored_file(keys) -> Path:
    keys.dir.mkdir()
    path = keys.dir / "tavily.cred"
    path.write_text("encrypted")
    return path


def test_the_store_is_chosen_by_platform(keys, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert keys.module.store_kind() == "keychain"
    monkeypatch.setattr(sys, "platform", "win32")
    assert keys.module.store_kind() == "windows"
    monkeypatch.setattr(sys, "platform", "linux")
    assert keys.module.store_kind() == "systemd"


def test_an_environment_variable_wins_and_nothing_is_run(keys, monkeypatch):
    use(keys, "systemd")
    monkeypatch.setenv("TAVILY_API_KEY", "  from-env  ")
    assert keys.module.get_key("tavily") == "from-env" and keys.runs == []


def test_the_variable_name_comes_from_the_key_name(keys):
    assert keys.module.env_name("tavily") == "TAVILY_API_KEY"
    assert keys.module.env_name("my-key") == "MY_KEY_API_KEY"


def test_systemd_decrypts_the_stored_file_for_this_user(keys):
    use(keys, "systemd")
    path = stored_file(keys)
    assert keys.module.get_key("tavily") == DUMMY
    assert keys.runs == [[keys.module.SYSTEMD_CREDS, "--user", "--name=tavily", "decrypt", str(path), "-"]]


def test_a_missing_systemd_file_means_not_set_and_nothing_is_run(keys):
    use(keys, "systemd")
    with pytest.raises(keys.module.KeyNotSet):
        keys.module.get_key("tavily")
    assert keys.runs == []


def test_a_key_that_cannot_be_decrypted_is_an_error_that_never_shows_it(keys):
    use(keys, "systemd")
    stored_file(keys)
    keys.reply.update(returncode=1, stdout=DUMMY.encode())
    with pytest.raises(RuntimeError, match="could not be decrypted") as error:
        keys.module.get_key("tavily")
    assert not isinstance(error.value, keys.module.KeyNotSet) and DUMMY not in str(error.value)


def test_a_timeout_is_an_error(keys):
    use(keys, "systemd")
    stored_file(keys)

    def hang(argv, **_kwargs):
        raise subprocess.TimeoutExpired(argv, 10)

    keys.mp.setattr(keys.module.subprocess, "run", hang)
    with pytest.raises(RuntimeError, match="could not be read"):
        keys.module.get_key("tavily")


def test_the_keychain_is_asked_for_the_key_by_service_and_name(keys):
    use(keys, "keychain")
    assert keys.module.get_key("tavily") == DUMMY
    assert keys.runs == [[keys.module.SECURITY, "find-generic-password", "-s", "reachy-tools", "-a", "tavily", "-w"]]


def test_the_keychain_service_can_be_changed_so_tests_never_touch_real_keys(keys, monkeypatch):
    use(keys, "keychain")
    monkeypatch.setenv("REACHY_TOOLS_KEYCHAIN_SERVICE", "reachy-tools-test")
    keys.module.get_key("tavily")
    assert keys.runs[0][3] == "reachy-tools-test"


def test_a_key_absent_from_the_keychain_is_not_set_and_other_failures_are_errors(keys):
    use(keys, "keychain")
    keys.reply.update(returncode=44, stdout=b"")
    with pytest.raises(keys.module.KeyNotSet):
        keys.module.get_key("tavily")
    keys.reply.update(returncode=1)
    with pytest.raises(RuntimeError, match="could not be decrypted"):
        keys.module.get_key("tavily")


def test_windows_reads_the_credential_manager_entry(keys):
    use(keys, "windows")
    asked: list[str] = []
    keys.mp.setattr(keys.module, "_cred_read", lambda target: asked.append(target) or DUMMY.encode("utf-16-le"))
    assert keys.module.get_key("tavily") == DUMMY and asked == ["reachy-tools/tavily"]


def test_a_credential_absent_from_windows_is_not_set(keys):
    use(keys, "windows")
    keys.mp.setattr(keys.module, "_cred_read", lambda target: None)
    with pytest.raises(keys.module.KeyNotSet):
        keys.module.get_key("tavily")


def test_systemd_stores_the_key_through_stdin_in_an_owner_only_file(keys):
    use(keys, "systemd")
    keys.module.set_key("tavily", "abc")
    temporary = keys.dir / ".tavily.cred.new"
    assert keys.runs == [[keys.module.SYSTEMD_CREDS, "--user", "encrypt", "--name=tavily", "-", str(temporary)]]
    assert keys.inputs == [b"abc"] and all("abc" not in part for part in keys.runs[0])
    final = keys.dir / "tavily.cred"
    assert final.exists() and not temporary.exists()
    assert final.stat().st_mode & 0o777 == 0o600 and keys.dir.stat().st_mode & 0o777 == 0o700


def test_the_keychain_is_given_the_key_on_stdin_never_in_arguments(keys):
    use(keys, "keychain")
    keys.module.set_key("tavily", "abc")
    assert keys.runs == [[keys.module.SECURITY, "-i"]]
    assert keys.inputs == [b'add-generic-password -U -s "reachy-tools" -a "tavily" -w "abc"\n']


@pytest.mark.parametrize("unsafe", ['bad"key', "back\\slash", "new\nline", "has space", ""])
def test_a_key_the_keychain_cannot_safely_take_is_refused_before_anything_runs(keys, unsafe):
    use(keys, "keychain")
    with pytest.raises(ValueError, match="Keychain"):
        keys.module.set_key("tavily", unsafe)
    assert keys.runs == []


def test_windows_stores_and_deletes_through_the_credential_manager(keys):
    use(keys, "windows")
    written: list[tuple[str, str]] = []
    keys.mp.setattr(keys.module, "_cred_write", lambda target, key: written.append((target, key)))
    keys.mp.setattr(keys.module, "_cred_delete", lambda target: target == "reachy-tools/tavily")
    keys.module.set_key("tavily", "abc")
    assert written == [("reachy-tools/tavily", "abc")]
    keys.module.delete_key("tavily")
    with pytest.raises(keys.module.KeyNotSet):
        keys.module.delete_key("other")


def test_deleting_removes_the_file_or_the_keychain_item_and_a_missing_key_is_not_set(keys):
    use(keys, "systemd")
    path = stored_file(keys)
    keys.module.delete_key("tavily")
    assert not path.exists()
    with pytest.raises(keys.module.KeyNotSet):
        keys.module.delete_key("tavily")
    use(keys, "keychain")
    keys.module.delete_key("tavily")
    assert keys.runs == [[keys.module.SECURITY, "delete-generic-password", "-s", "reachy-tools", "-a", "tavily"]]
    keys.reply["returncode"] = 44
    with pytest.raises(keys.module.KeyNotSet):
        keys.module.delete_key("tavily")


def test_only_the_robot_can_list_stored_names(keys):
    use(keys, "systemd")
    stored_file(keys)
    (keys.dir / "other.cred").write_text("x")
    assert keys.module.stored_names() == ["other", "tavily"]
    for kind in ("keychain", "windows"):
        use(keys, kind)
        with pytest.raises(keys.module.ListNotSupported):
            keys.module.stored_names()


def command(keys, capsys, monkeypatch, *args: str, stdin: str = ""):
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    code = keys.module.main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_the_command_adds_a_key_then_checks_it(keys, capsys, monkeypatch):
    use(keys, "systemd")
    code, out, _ = command(keys, capsys, monkeypatch, "add", "tavily", stdin="abc\n")
    assert code == 0 and "OK: the tavily key is stored and decrypts." in out and "abc" not in out
    assert (keys.dir / "tavily.cred").exists()


def test_the_command_refuses_an_empty_key_and_stores_nothing(keys, capsys, monkeypatch):
    use(keys, "systemd")
    code, _, err = command(keys, capsys, monkeypatch, "add", "tavily", stdin="\n")
    assert code == 1 and "No key entered" in err and not (keys.dir / "tavily.cred").exists()


def test_the_command_reports_a_missing_key_for_check_and_remove(keys, capsys, monkeypatch):
    use(keys, "systemd")
    code, _, err = command(keys, capsys, monkeypatch, "check", "tavily")
    assert code == 1 and "Problem: the tavily key is missing" in err
    code, _, err = command(keys, capsys, monkeypatch, "remove", "tavily")
    assert code == 1 and "No tavily key is stored." in err


def test_the_command_removes_a_key_and_lists_names_on_the_robot(keys, capsys, monkeypatch):
    use(keys, "systemd")
    stored_file(keys)
    assert command(keys, capsys, monkeypatch, "list")[:2] == (0, "tavily\n")
    code, out, _ = command(keys, capsys, monkeypatch, "remove", "tavily")
    assert code == 0 and "Removed the tavily key." in out
    assert command(keys, capsys, monkeypatch, "list")[:2] == (0, "No keys stored.\n")


def test_listing_elsewhere_says_it_is_not_available(keys, capsys, monkeypatch):
    use(keys, "keychain")
    code, _, err = command(keys, capsys, monkeypatch, "list")
    assert code == 1 and "not available" in err and "check NAME" in err


def test_the_command_refuses_a_bad_name_or_no_arguments(keys, capsys, monkeypatch):
    use(keys, "systemd")
    assert command(keys, capsys, monkeypatch, "add", "Bad-Name")[0] == 2
    assert command(keys, capsys, monkeypatch, "check")[0] == 2
    code, _, err = command(keys, capsys, monkeypatch)
    assert code == 2 and "add NAME" in err


def test_the_wrapper_scripts_just_call_the_python_command():
    scripts = TOOLS.parent / "scripts"
    sh, bat = (scripts / "keys.sh").read_text(), (scripts / "keys.bat").read_text()
    assert "reachy_lib/keys.py" in sh and '"$@"' in sh
    assert "reachy_lib\\keys.py" in bat and "%*" in bat
