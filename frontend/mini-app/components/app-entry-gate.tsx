"use client";

import { useEffect, useState } from "react";
import { getStartParamFallback, initTelegram } from "@/lib/telegram";
import { FeedStartApp } from "./feed-startapp-app";
import { GenerationActionGate } from "./generation-action-app";
import { ProfileStartApp } from "./profile-startapp-app";

const POST_LINK = /^feed_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_ref_(\d+)$/i;
const REMIX_LINK = /^remix_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_ref_(\d+)$/i;
const TREND_LINK = /^trend_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i;
const LEGACY_PROFILE_LINK = /^posts_(\d+)_ref_(\d+)$/;
const PROFILE_LINK = /^profile_(\d+)(?:_ref_(\d+))?$/;
const CONSUMED_TREND_TARGET_KEY = "__roxy_consumed_trend_target";
const CONSUMED_PROFILE_TARGET_KEY = "__roxy_consumed_profile_target";
const EXPLICIT_START_PARAM_NAMES = ["start_payload", "startapp"];

type Target =
  | { kind: "post" | "remix"; generationId: string; referralCode: string }
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
  // Only a product-owned payload in the *current* URL is a fresh explicit launch.
  // Telegram keeps SDK start_param and the initial launch snapshot alive for the
  // whole WebView session, so treating those persistent values as explicit would
  // reopen an already-consumed trend/profile every time the user presses Back.
  for (const raw of [window.location.search, window.location.hash]) {
    const params = new URLSearchParams(String(raw || "").replace(/^[?#]/, ""));
    for (const name of EXPLICIT_START_PARAM_NAMES) {
      if (String(params.get(name) || "").trim() === payload) return true;
    }
  }
  return false;
}

function prepareTrendReturnLocation(): void {
  // A shared trend starts on the Main Mini App URL and immediately redirects to
  // the standalone trend page. Store a clean Catalog return URL before Telegram's
  // navigation tracker snapshots it; otherwise native Back returns to the same
  // startapp URL and opens the trend again in a loop.
  const url = new URL(window.location.href);
  url.searchParams.delete("startapp");
  url.searchParams.delete("start_payload");
  if (!url.searchParams.has("route")) url.searchParams.set("route", "catalog");
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function EntryBackMarker() {
  // telegram.ts treats an overlay as a transient layer. The marker is invisible,
  // but keeps Telegram's native Back button visible while a deep-link gate/splash
  // is active. Close chrome is reserved for the actually rendered Catalog root.
  return <span className="overlay" aria-hidden="true" style={{ display: "none" }} />;
}

function profileTarget(referralCode: string, payload: string): Target | null {
  // Telegram retains initDataUnsafe.start_param for the lifetime of the WebView.
  // Once the public profile has been shown, internal ROXY navigation must not
  // bounce back to it. A fresh explicit deep-link URL is still honored.
  if (targetConsumed(CONSUMED_PROFILE_TARGET_KEY, payload) && !explicitLaunchCarries(payload)) return null;
  return { kind: "profile", referralCode, payload };
}

function parseTarget(): Target | null {
  const payload = getStartParamFallback();
  if (POST_LINK.test(payload)) {
    const match = POST_LINK.exec(payload)!;
    return { kind: "post", generationId: match[1], referralCode: match[2] };
  }
  if (REMIX_LINK.test(payload)) {
    const match = REMIX_LINK.exec(payload)!;
    return { kind: "remix", generationId: match[1], referralCode: match[2] };
  }
  if (TREND_LINK.test(payload)) {
    // Telegram keeps start_param alive for the WebView session. Ignore that stale
    // value when the user returns to ROXY, but honor an explicit fresh deep-link
    // URL even when it points to the same trend again.
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
  if (target?.kind === "trend") return <TrendStartApp trendId={target.trendId} payload={target.payload} />;
  if (target?.kind === "post" || target?.kind === "remix") {
    return <><EntryBackMarker /><FeedStartApp generationId={target.generationId} referralCode={target.referralCode} intent={target.kind} /></>;
  }
  return <GenerationActionGate />;
}