"use client";

import { useEffect, useState } from "react";
import { initTelegram, telegram } from "@/lib/telegram";
import { FeedStartApp } from "./feed-startapp-app";
import { GenerationActionGate } from "./generation-action-app";

const FEED_LINK = /^feed_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_ref_(\d+)$/i;

type Target = { generationId: string; referralCode: string };

function parseTarget(): Target | null {
  const url = new URL(window.location.href);
  const payload = telegram()?.initDataUnsafe?.start_param || url.searchParams.get("tgWebAppStartParam") || "";
  const match = FEED_LINK.exec(payload);
  return match ? { generationId: match[1], referralCode: match[2] } : null;
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

  if (!ready) return <div className="splash" role="status"><strong>ROXY</strong><small>Открываю работу…</small></div>;
  return target ? <FeedStartApp {...target} /> : <GenerationActionGate />;
}
