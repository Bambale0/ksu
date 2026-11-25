"""Short-lived, browser-bound Telegram chat approval. No wallet mutation."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
import re
import secrets

TTL = 300
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}\Z")
COOKIE = "roxy_telegram_approval"
ROOT = "/api/v1/browser-auth/approval"
logger = logging.getLogger("ksu.browser_approval")


@dataclass(frozen=True)
class ApprovalLimits:
    browser_limit: int = 5
    network_limit: int = 300
    window_seconds: int = 600
    revision: int = 1


def audit(ticket: str, action: str, outcome: str, owner: int) -> None:
    """Correlate decisions/claims without logging the challenge or credentials."""
    logger.info(
        "browser_approval action=%s outcome=%s telegram_id=%s approval_id=%s",
        action, outcome, owner, digest(ticket)[:24],
        extra={"approval_action": action, "approval_outcome": outcome,
               "telegram_id": owner, "approval_id": digest(ticket)[:24]},
    )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def key(ticket: str) -> str:
    return "roxy:browser-approval:v1:" + digest(ticket)


def split_cookie(raw: str) -> tuple[str, str] | None:
    parts = raw.split(".")
    if len(parts) != 2 or not all(TOKEN_RE.fullmatch(p) for p in parts):
        return None
    return parts[0], parts[1]


# All state changes are atomic; HSET preserves the initial five-minute expiry.
# Only the private Telegram update can bind/decide an owner. The browser can
# claim an approved request once, with its independent HttpOnly proof.
TRANSITION = """
local k = KEYS[1]
local action, proof, owner, payload = ARGV[1], ARGV[2], ARGV[3], ARGV[4]
local state = redis.call('HGET', k, 'state')
if not state then return {'expired'} end
local bound = redis.call('HGET', k, 'owner') or ''
if action == 'bind' then
  if state ~= 'pending' or (bound ~= '' and bound ~= owner) then return {'unavailable'} end
  redis.call('HSET',k,'owner',owner)
  return {'pending', redis.call('HGET',k,'code'),redis.call('HGET',k,'purpose')}
elseif action == 'approve' or action == 'deny' then
  if state ~= 'pending' or bound ~= owner or bound == '' then return {'unavailable'} end
  local next = action == 'approve' and 'approved' or 'denied'
  redis.call('HSET',k,'state',next)
  if next == 'approved' then redis.call('HSET',k,'user',payload) end
  return {next,redis.call('HGET',k,'purpose')}
end
if redis.call('HGET',k,'proof') ~= proof then return {'expired'} end
if action == 'status' then
  return {state,redis.call('HGET',k,'code'),redis.call('HGET',k,'purpose'),tostring(redis.call('TTL',k))}
elseif action == 'cancel' then
  if state == 'pending' or state == 'approved' then redis.call('HSET',k,'state','denied'); return {'denied'} end
elseif action == 'claim' and state == 'approved' then
  local user = redis.call('HGET',k,'user')
  redis.call('HSET',k,'state','consumed')
  redis.call('HDEL',k,'user')
  return {'consumed',user,redis.call('HGET',k,'purpose')}
end
return {'unavailable'}
"""

ISSUE = """
local n = redis.call('INCR',KEYS[2])
if n == 1 then redis.call('EXPIRE',KEYS[2],tonumber(ARGV[4])) end
if n > tonumber(ARGV[5]) then return 0 end
if KEYS[3] ~= KEYS[1] and redis.call('HGET',KEYS[3],'proof') == ARGV[1] then
  local old=redis.call('HGET',KEYS[3],'state')
  if old == 'pending' or old == 'approved' then redis.call('HSET',KEYS[3],'state','denied') end
end
redis.call('HSET',KEYS[1],'proof',ARGV[1],'code',ARGV[2],'purpose',ARGV[3],'state','pending')
redis.call('EXPIRE',KEYS[1],300)
return 1
"""


async def issue(redis, prior: tuple[str, str] | None, purpose: str, client: str,
                *, limits: ApprovalLimits = ApprovalLimits()):
    ticket = secrets.token_urlsafe(32)
    proof = prior[1] if prior else secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1_000_000):06d}"
    rate = f"roxy:browser-approval:rate:{limits.revision}:" + digest(proof)
    # Bound anonymous issuance too. Reverse proxy rate limits remain useful.
    ip_rate = f"roxy:browser-approval:network:{limits.revision}:" + hashlib.sha256(client.encode()).hexdigest()
    n = await redis.eval(
        "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],tonumber(ARGV[1])) end; return n",
        1, ip_rate, limits.window_seconds,
    )
    if int(n) > limits.network_limit:
        return None
    ok = await redis.eval(ISSUE, 3, key(ticket), rate, key(prior[0]) if prior else key(ticket),
                          digest(proof), code, purpose, limits.window_seconds, limits.browser_limit)
    if not ok:
        return None
    return ticket, proof, code


async def transition(redis, ticket: str, action: str, *, proof: str = "", owner: int = 0, user=None):
    if not TOKEN_RE.fullmatch(ticket):
        return ["expired"]
    result = await redis.eval(TRANSITION, 1, key(ticket), action, digest(proof) if proof else "",
                              str(owner), json.dumps(user or {}, ensure_ascii=False))
    decoded = [item.decode() if isinstance(item, bytes) else item for item in result]
    if action in {"approve", "deny"}:
        audit(ticket, action, decoded[0], owner)
    return decoded
