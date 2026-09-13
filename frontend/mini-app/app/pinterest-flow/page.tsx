"use client";

import { useEffect, useState } from "react";

import PinterestRepeatPage from "../pinterest-repeat/page";

export default function LegacyPinterestFlowPage() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const url = new URL(window.location.href);
    const trendId = url.searchParams.get("id")?.trim();
    if (trendId) {
      window.location.replace(`/mini-app/trend/?id=${encodeURIComponent(trendId)}`);
      return;
    }
    setReady(true);
  }, []);

  if (!ready) return null;
  return <PinterestRepeatPage />;
}
