"use client";

import { useMemo } from "react";

import { PrivateRepeatStartApp } from "@/components/private-repeat-startapp";

const TOKEN_RE = /^[0-9a-f]{32}_[A-Za-z0-9_-]{16}$/;

function tokenFromLocation(): string {
  if (typeof window === "undefined") return "";
  const token = new URL(window.location.href).searchParams.get("token") || "";
  return TOKEN_RE.test(token) ? token : "";
}

export default function RepeatPage() {
  const token = useMemo(tokenFromLocation, []);

  if (!token) {
    return <div className="splash" role="alert"><strong>ROXY</strong><small>Ссылка повтора повреждена или устарела.</small></div>;
  }

  return <PrivateRepeatStartApp token={token} />;
}
