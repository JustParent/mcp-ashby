"""End-to-end stdio smoke test against an *installed* ashby server.

The offline contract tests import `src.ashby.server` from the working tree. That
cannot catch a failure in the packaged artifact, which is where production broke:
an incompatible `mcp` resolved at install time made the module raise at import,
so the process died before answering `initialize`.

This probe spawns the installed console script exactly as an MCP client does,
speaks real JSON-RPC over stdio, and fails loudly with the child's stderr.

Usage:
    python tests/smoke_stdio.py [path/to/ashby]

Not collected by pytest: the filename does not match `test_*.py`, matching the
convention already used by `stub_ashby.py`.
"""
import json
import os
import signal
import subprocess
import sys

# Tools that must be present for the server to be considered functional. A short
# anchor set rather than the full list, so adding a tool does not break the smoke
# test; `test_tool_contract.py` is what exhaustively pins the surface.
ANCHOR_TOOLS = {
    "search_candidates",
    "get_candidate_info",
    "list_applications",
    "list_openings",
    "get_offer_info",
}

TIMEOUT_SECONDS = 60


class SmokeFailure(Exception):
    pass


def _readline(proc, what):
    line = proc.stdout.readline()
    if not line:
        raise SmokeFailure(f"server closed stdout while waiting for {what}")
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"non-JSON reply to {what}: {line[:400]!r}") from exc


def main(argv):
    exe = argv[1] if len(argv) > 1 else "ashby"

    # A server that hangs instead of replying is a failure, not a reason to stall
    # CI until the job-level timeout kills it with no diagnostic.
    def _timeout(signum, frame):
        raise SmokeFailure(f"no reply within {TIMEOUT_SECONDS}s")

    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(TIMEOUT_SECONDS)

    # connect() only reads the env var and builds an auth header; it performs no
    # network I/O. A dummy key keeps startup quiet without reaching Ashby.
    env = dict(os.environ, ASHBY_API_KEY=os.getenv("ASHBY_API_KEY", "smoke-test-dummy-key"))

    proc = subprocess.Popen(
        [exe],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    try:
        send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "ci-smoke", "version": "1.0"},
            },
        })
        init = _readline(proc, "initialize")
        if "result" not in init:
            raise SmokeFailure(f"initialize did not return a result: {init}")
        info = init["result"].get("serverInfo", {})
        print(f"initialize OK -> {info.get('name')} {info.get('version')}")

        send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        listed = _readline(proc, "tools/list")
        if "result" not in listed:
            raise SmokeFailure(f"tools/list did not return a result: {listed}")

        tools = listed["result"].get("tools", [])
        if not tools:
            raise SmokeFailure("tools/list returned no tools")

        malformed = [
            t.get("name", "<unnamed>") for t in tools
            if not t.get("name") or not isinstance(t.get("inputSchema"), dict)
        ]
        if malformed:
            raise SmokeFailure(f"tools missing a name or inputSchema: {malformed}")

        names = {t["name"] for t in tools}
        missing = sorted(ANCHOR_TOOLS - names)
        if missing:
            raise SmokeFailure(f"expected tools absent from tools/list: {missing}")

        print(f"tools/list OK -> {len(tools)} tools, all anchors present")
        return 0

    finally:
        signal.alarm(0)
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        stderr = proc.stderr.read()
        if stderr.strip():
            # The production failure surfaced only here, so never swallow it.
            print("--- server stderr ---", file=sys.stderr)
            print(stderr.strip(), file=sys.stderr)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except SmokeFailure as exc:
        print(f"SMOKE FAILURE: {exc}", file=sys.stderr)
        sys.exit(1)
