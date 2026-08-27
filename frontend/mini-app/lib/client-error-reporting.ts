import { telegramHeaders } from "./telegram";

export type ClientErrorKind = "window_error" | "unhandled_rejection" | "react_error";

type ClientErrorExtras = {
  componentStack?: string | null;
  digest?: string | null;
};

const MAX_REPORTS_PER_PAGE = 8;
const seen = new Set<string>();
let sentCount = 0;

function clip(value: unknown, limit: number): string {
  return String(value ?? "").slice(0, limit);
}

function errorMessage(value: unknown): string {
  if (value instanceof Error) return value.message || value.name || "Unknown client error";
  if (typeof value === "string") return value || "Unknown client error";
  try {
    const serialized = JSON.stringify(value);
    return serialized && serialized !== "{}" ? serialized : "Unknown client error";
  } catch {
    return "Unknown client error";
  }
}

function errorStack(value: unknown): string {
  return value instanceof Error ? clip(value.stack || "", 6000) : "";
}

export function reportClientError(
  kind: ClientErrorKind,
  error: unknown,
  extras: ClientErrorExtras = {},
): void {
  if (typeof window === "undefined" || typeof navigator === "undefined") return;

  const message = clip(errorMessage(error), 1000) || "Unknown client error";
  const stack = errorStack(error);
  const signature = `${kind}|${message}|${stack.slice(0, 300)}`;
  if (seen.has(signature) || sentCount >= MAX_REPORTS_PER_PAGE) return;

  seen.add(signature);
  sentCount += 1;

  const body = {
    kind,
    message,
    stack: stack || null,
    component_stack: extras.componentStack ? clip(extras.componentStack, 6000) : null,
    pathname: clip(window.location.pathname || "/mini-app/", 256),
    user_agent: clip(navigator.userAgent || "", 512),
    platform: clip(navigator.platform || "", 64),
    viewport_width: Math.max(0, Math.round(window.innerWidth || 0)),
    viewport_height: Math.max(0, Math.round(window.innerHeight || 0)),
    device_pixel_ratio: Number.isFinite(window.devicePixelRatio) ? window.devicePixelRatio : null,
    digest: extras.digest ? clip(extras.digest, 256) : null,
  };

  try {
    void fetch("/api/v1/client-logs", {
      method: "POST",
      headers: telegramHeaders(true),
      credentials: "same-origin",
      body: JSON.stringify(body),
    }).catch(() => undefined);
  } catch {
    // Diagnostics must never cause or amplify the original client failure.
  }
}
