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

type Target =
  | { kind: "post" | "remix"; generationId: string; referralCode: string }
  | { kind: "trend"; trendId: string }
  | { kind: "profile"; referralCode: string };

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
    const match = TREND_LINK.exec(payload)!;
    return { kind: "trend", trendId: match[1] };
  }
  if (LEGACY_PROFILE_LINK.test(payload)) {
    const match = LEGACY_PROFILE_LINK.exec(payload)!;
    return match[1] === match[2] ? { kind: "profile", referralCode: match[1] } : null;
  }
  if (PROFILE_LINK.test(payload)) {
    const match = PROFILE_LINK.exec(payload)!;
    const referralCode = match[2] || match[1];
    return match[1] === referralCode ? { kind: "profile", referralCode: match[1] } : null;
  }
  return null;
}

function TrendStartApp({ trendId }: { trendId: string }) {
  useEffect(() => {
    window.location.replace(`/mini-app/trend/?id=${encodeURIComponent(trendId)}`);
  }, [trendId]);
  return <div className="splash" role="status"><strong>ROXY</strong><small>Открываю тренд…</small></div>;
}

export function AppEntryGate() {
  const [ready, setReady] = useState(false);
  const [target, setTarget] = useState<Target | null>(null);

  useEffect(() => {
    const tg = initTelegram();
    tg?.ready?.();
    tg?.expand?.();
    setTarget(parseTarget());
    setReady(true);
  }, []);

  if (!ready) return <div className="splash" role="status"><strong>ROXY</strong><small>Открываю ссылку…</small></div>;
  if (target?.kind === "profile") return <ProfileStartApp referralCode={target.referralCode} />;
  if (target?.kind === "trend") return <TrendStartApp trendId={target.trendId} />;
  if (target?.kind === "post" || target?.kind === "remix") {
    return <FeedStartApp generationId={target.generationId} referralCode={target.referralCode} intent={target.kind} />;
  }
  return <GenerationActionGate />;
}
