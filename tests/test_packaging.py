"""Packaging guards.

The server is installed in production with `uvx --from mcp-ashby-connector ashby`.
uvx resolves from the wheel's declared dependency metadata and **ignores uv.lock**,
so an unpinned dependency there is resolved fresh to the newest release on every
install. mcp 2.0 removed the low-level `Server.list_tools()` / `Server.call_tool()`
decorators that this module applies at import time, which crashed the server before
it could answer `initialize`.

These tests assert the declared constraints keep that from happening again.
"""
import pathlib
import re

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())

# Every mcp API this module reaches for at import time or in run().
REQUIRED_SERVER_API = ("list_tools", "call_tool", "get_capabilities", "run")


def _requirements() -> dict[str, str]:
    """Declared runtime dependencies, mapped name -> full requirement string."""
    out = {}
    for req in PYPROJECT["project"]["dependencies"]:
        name = re.split(r"[<>=!~\[; ]", req, maxsplit=1)[0].strip().lower()
        out[name] = req
    return out


def _inline_script_requirements() -> dict[str, str]:
    """Dependencies from the PEP 723 inline metadata block at the top of server.py.

    `uv run src/ashby/server.py` resolves from this block, not from pyproject.toml,
    so it is a second independent path to the same breakage.
    """
    text = (ROOT / "src" / "ashby" / "server.py").read_text()
    block = re.search(r"# /// script\n(.*?)# ///", text, re.S)
    assert block, "PEP 723 inline script metadata block not found in server.py"
    body = "".join(line.lstrip("#").strip() for line in block.group(1).splitlines())
    deps = re.findall(r'"([^"]+)"', body)
    return {re.split(r"[<>=!~\[; ]", d, maxsplit=1)[0].strip().lower(): d for d in deps}


@pytest.mark.parametrize("source", ["pyproject", "inline-script"])
def test_mcp_excludes_the_incompatible_major(source):
    """mcp must be capped below 2.0, which removed the decorator API used here."""
    reqs = _requirements() if source == "pyproject" else _inline_script_requirements()
    assert "mcp" in reqs, f"mcp not declared in {source}"
    spec = reqs["mcp"]
    assert "<2" in spec.replace(" ", ""), (
        f"{source} declares {spec!r}: unbounded, so a fresh install resolves mcp 2.x, "
        "which removed Server.list_tools()/call_tool() and crashes at import."
    )


@pytest.mark.parametrize("source", ["pyproject", "inline-script"])
def test_every_runtime_dependency_is_bounded(source):
    """No runtime dependency may float free; a major bump must not reach prod unreviewed."""
    reqs = _requirements() if source == "pyproject" else _inline_script_requirements()
    unbounded = [
        spec for spec in reqs.values()
        if not re.search(r"[<>=~!]", spec)
    ]
    assert not unbounded, (
        f"{source} declares unbounded dependencies: {unbounded}. "
        "uvx ignores uv.lock, so these resolve to the newest release on every install."
    )


def test_installed_server_exposes_the_api_this_module_uses():
    """The resolved mcp must actually provide the decorators server.py applies."""
    from mcp.server import Server

    missing = [name for name in REQUIRED_SERVER_API if not hasattr(Server, name)]
    assert not missing, (
        f"Installed mcp is missing {missing} on the low-level Server. "
        "This is the prod failure: the decorator is applied at import time."
    )
