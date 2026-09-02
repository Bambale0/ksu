"use client";

import { useEffect, useState } from "react";
import { getStartParamFallback, initTelegram } from "@/lib/telegram";
import { FeedStartApp } from "./feed-startapp-app";
import { GenerationActionGate } from "./generation-action-app";
import { PrivateRepeatStartApp } from "./private-repeat-startapp";
import { ProfileStartApp } from "./profile-startapp-app";

const POST_LINK = /^feed_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_ref_(\d+)$/i;
const REMIX_LINK = /^remix_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_ref_(\d+)$/i;
const PRIVATE_REPEAT_LINK = /^repeat_([0-9a-f]{32}_[A-Za-z0-9_-]{16})$/;
const TREND_LINK = /^trend_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:_ref_(\d+))?$/i;
const LEGACY_PROFILE_LINK = /^posts_(\d+)_ref_(\d+)$/;
const PROFILE_LINK = /^profile_(\d+)(?:_ref_(\d+))?$/;
const CONSUMED_TREND_TARGET_KEY = "__roxy_consumed_trend_target";
const CONSUMED_PROFILE_TARGET_KEY = "__roxy_consumed_profile_target";
const EXPLICIT_START_PARAM_NAMES = ["start_payload", "startapp"];

type Target =
  | { kind: "post" | "remix"; generationId: string; referralCode: string }
  | { kind: "repeat"; token: string; payload: string }
  | { kind: "trend"; trendId: string; payload: string }
  | { kind: "profile"; referralCode: string; payload: string };

function targetConsumed(storageKey: string, payload: string): boolean {
  try {
    return window.sessionStorage.getItem(storageKey) === payload;
  } catch {
    return false;
  }
}

function markTargetConsumed(storageKey: string, payload: string): void {
  try {
    window.sessionStorage.setItem(storageKey, payload);
  } catch {
    // Some restrictive WebViews disable sessionStorage; navigation still works.
  }
}

function explicitLaunchCarries(payload: string): boolean {
  // Only product-owned payloads in the current URL count as a fresh explicit
  // launch. Telegram keeps initDataUnsafe.start_param alive for the WebView
  // session, so treating that sticky SDK value as explicit would reopen a
  // consumed trend/profile every time the user presses native Back.
  for (const raw of [window.location.search, window.location.hash]) {
    const params = new URLSearchParams(String(raw || "").replace(/^[?#]/, ""));
    for (const name of EXPLICIT_START_PARAM_NAMES) {
      if (String(params.get(name) || "").trim() === payload) return true;
    }
  }
  return false;
}

function prepareTrendReturnLocation(): void {
  // Store a clean Catalog return URL before the trend page is opened. Without
  // this, Telegram can return to the same ?startapp=trend_* URL and immediately
  // replay the deep link in a loop.
  const url = new URL(window.location.href);
  url.searchParams.delete("startapp");
  url.searchParams.delete("start_payload");
  if (!url.searchParams.has("route")) url.searchParams.set("route", "catalog");
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function EntryBackMarker() {
  // telegram.ts treats an overlay as a transient layer. This invisible marker
  // keeps native Back visible while the deep-link gate/splash is active; Close
  // chrome is reserved for an actually rendered root screen.
  return <span className="overlay" aria-hidden="true" style={{ display: "none" }} />;
}

function profileTarget(referralCode: string, payload: string): Target | null {
  if (targetConsumed(CONSUMED_PROFILE_TARGET_KEY, payload) && !explicitLaunchCarries(payload)) return null;
  return { kind: "profile", referralCode, payload };
}

function parseTarget(): Target | null {
  // Recovery from the backend onboarding gate must win over Telegram's retained
  // start_param. Otherwise a feed/remix deep link can reopen itself forever and
  // prevent a first-time user from ever reaching onboarding.
  const current = new URL(window.location.href);
  if (current.searchParams.get("onboarding") === "1") return null;

  const payload = getStartParamFallback();
  if (POST_LINK.test(payload)) {
    const match = POST_LINK.exec(payload)!;
    return { kind: "post", generationId: match[1], referralCode: match[2] };
  }
  if (REMIX_LINK.test(payload)) {
    const match = REMIX_LINK.exec(payload)!;
    return { kind: "remix", generationId: match[1], referralCode: match[2] };
  }
  if (PRIVATE_REPEAT_LINK.test(payload)) {
    // Telegram keeps start_param sticky for the WebView session. Once ROXY has
    // navigated to a concrete customer route (history/home/create), do not reopen
    // the repeat unless the current URL explicitly carries the repeat payload.
    if (current.searchParams.has("route") && !explicitLaunchCarries(payload)) return null;
    const match = PRIVATE_REPEAT_LINK.exec(payload)!;
    return { kind: "repeat", token: match[1], payload };
  }
  if (TREND_LINK.test(payload)) {
    if (targetConsumed(CONSUMED_TREND_TARGET_KEY, payload) && !explicitLaunchCarries(payload)) return null;
    const match = TREND_LINK.exec(payload)!;
    return { kind: "trend", trendId: match[1], payload };
  }
  if (LEGACY_PROFILE_LINK.test(payload)) {
    const match = LEGACY_PROFILE_LINK.exec(payload)!;
    return match[1] === match[2] ? profileTarget(match[1], payload) : null;
  }
  if (PROFILE_LINK.test(payload)) {
    const match = PROFILE_LINK.exec(payload)!;
    const referralCode = match[2] || match[1];
    return match[1] === referralCode ? profileTarget(match[1], payload) : null;
  }
  return null;
}

function TrendStartApp({ trendId, payload }: { trendId: string; payload: string }) {
  useEffect(() => {
    markTargetConsumed(CONSUMED_TREND_TARGET_KEY, payload);
    window.location.replace(`/mini-app/trend/?id=${encodeURIComponent(trendId)}`);
  }, [payload, trendId]);
  return <div className="splash" role="status"><EntryBackMarker /><strong>ROXY</strong><small>Открываю тренд…</small></div>;
}

function ProfileTarget({ referralCode, payload }: { referralCode: string; payload: string }) {
  useEffect(() => {
    markTargetConsumed(CONSUMED_PROFILE_TARGET_KEY, payload);
  }, [payload]);
  return <><EntryBackMarker /><ProfileStartApp referralCode={referralCode} /></>;
}

function PrivateRepeatTarget({ token }: { token: string }) {
  return <><EntryBackMarker /><PrivateRepeatStartApp token={token} /></>;
}

export function AppEntryGate() {
  const [ready, setReady] = useState(false);
  const [target, setTarget] = useState<Target | null>(null);

  useEffect(() => {
    const parsed = parseTarget();
    if (parsed?.kind === "trend") prepareTrendReturnLocation();
    const tg = initTelegram();
    tg?.ready?.();
    tg?.expand?.();
    setTarget(parsed);
    setReady(true);
  }, []);

  if (!ready) return <div className="splash" role="status"><EntryBackMarker /><strong>ROXY</strong><small>Открываю ссылку…</small></div>;
  if (target?.kind === "profile") return <ProfileTarget referralCode={target.referralCode} payload={target.payload} />;
  if (target?.kind === "repeat") return <PrivateRepeatTarget token={target.token} />;
  if (target?.kind === "trend") return <TrendStartApp trendId={target.trendId} payload={target.payload} />;
  if (target?.kind === "post" || target?.kind === "remix") {
    return <><EntryBackMarker /><FeedStartApp generationId={target.generationId} referralCode={target.referralCode} intent={target.kind} /></>;
  }
  return <GenerationActionGate />;
}
