"""Exercise the production Lua transitions against an isolated Redis socket."""
import asyncio
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import pytest


@pytest.mark.asyncio
async def test_atomic_chat_approval():
    if not shutil.which("redis-server") or not shutil.which("redis-cli"):
        pytest.skip("isolated redis executables unavailable")
    spec = importlib.util.spec_from_file_location("approval", Path(__file__).resolve().parents[1] / "app/services/browser_approval.py")
    approval = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(approval)
    with tempfile.TemporaryDirectory(prefix="roxy-auth-") as directory:
        socket = directory + "/redis.sock"
        server = subprocess.Popen(
            ["redis-server", "--port", "0", "--unixsocket", socket, "--unixsocketperm", "700",
             "--save", "", "--appendonly", "no", "--dir", directory],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(50):
                if Path(socket).exists():
                    break
                time.sleep(.05)

            class Redis:
                async def eval(self, script, num, *args):
                    proc = await asyncio.create_subprocess_exec(
                        "redis-cli", "-s", socket, "--json", "EVAL", script, str(num), *map(str, args),
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    )
                    out, err = await proc.communicate()
                    assert proc.returncode == 0, err.decode()
                    return json.loads(out)

            redis = Redis()
            ticket, proof, code = await approval.issue(redis, None, "payments", "qa")
            assert (await approval.transition(redis, ticket, "status", proof=proof))[0] == "pending"
            assert (await approval.transition(redis, ticket, "claim", proof=proof))[0] == "unavailable"
            assert (await approval.transition(redis, ticket, "bind", owner=123))[1] == code
            assert (await approval.transition(redis, ticket, "bind", owner=456))[0] == "unavailable"
            assert (await approval.transition(redis, ticket, "approve", owner=456))[0] == "unavailable"
            assert (await approval.transition(redis, ticket, "approve", owner=123, user={"id":123,"first_name":"QA"})) == ["approved","payments"]
            assert (await approval.transition(redis, ticket, "claim", proof="wrong"))[0] == "expired"
            claims = await asyncio.gather(*[approval.transition(redis,ticket,"claim",proof=proof) for _ in range(8)])
            assert sum(x[0] == "consumed" for x in claims) == 1
            assert (await approval.transition(redis, ticket, "approve", owner=123))[0] == "unavailable"
            t, p, _ = await approval.issue(redis, None, "studio", "qa")
            await approval.transition(redis, t, "bind", owner=123)
            assert (await approval.transition(redis, t, "deny", owner=123))[0] == "denied"
            assert (await approval.transition(redis, t, "claim", proof=p))[0] == "unavailable"
            t, p, _ = await approval.issue(redis, None, "studio", "qa")
            t2, p2, _ = await approval.issue(redis, (t,p), "payments", "qa")
            assert (await approval.transition(redis, t, "status", proof=p))[0] == "denied"
            assert (await approval.transition(redis, t2, "cancel", proof=p2))[0] == "denied"
            limits = approval.ApprovalLimits(browser_limit=1, network_limit=2, window_seconds=60, revision=2)
            limited = await approval.issue(redis, None, "studio", "limited", limits=limits)
            assert limited is not None
            assert await approval.issue(redis, limited[:2], "studio", "limited", limits=limits) is None
            assert await approval.issue(redis, None, "studio", "limited", limits=limits) is None
        finally:
            server.terminate()
            server.wait(timeout=5)
