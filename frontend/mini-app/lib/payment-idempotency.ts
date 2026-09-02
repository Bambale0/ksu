import { customerIdempotencyKey } from "@/lib/customer-api";

const STORAGE_KEY = "__roxy_payment_checkout_intent_v1";
const INTENT_TTL_MS = 2 * 60 * 60 * 1000;

type StoredIntent = {
  fingerprint: string;
  key: string;
  createdAt: number;
};

export type CheckoutIntent = {
  provider: string;
  packageId: string;
  currency: string;
  billingEmail?: string;
};

let memoryIntent: StoredIntent | null = null;

function storage(): Storage | null {
  if (typeof window === "undefined" || typeof localStorage === "undefined") return null;
  return localStorage;
}

function fingerprint(intent: CheckoutIntent): string {
  return JSON.stringify({
    provider: intent.provider,
    packageId: intent.packageId,
    currency: intent.currency.toUpperCase(),
    billingEmail: (intent.billingEmail || "").trim().toLowerCase(),
  });
}

function validIntent(value: Partial<StoredIntent> | null): value is StoredIntent {
  return Boolean(
    value
    && typeof value.fingerprint === "string"
    && typeof value.key === "string"
    && typeof value.createdAt === "number"
    && Date.now() - value.createdAt <= INTENT_TTL_MS,
  );
}

function removeStoredIntent(store: Storage | null): void {
  memoryIntent = null;
  if (!store) return;
  try {
    store.removeItem(STORAGE_KEY);
  } catch {
    // Storage can be unavailable in hardened/private WebViews. Checkout must still work.
  }
}

function readStoredIntent(): StoredIntent | null {
  const store = storage();
  if (store) {
    try {
      const parsed = JSON.parse(store.getItem(STORAGE_KEY) || "null") as Partial<StoredIntent> | null;
      if (validIntent(parsed)) {
        memoryIntent = parsed;
        return parsed;
      }
      removeStoredIntent(store);
    } catch {
      // Keep the in-memory fallback if this WebView blocks storage access.
    }
  }
  if (validIntent(memoryIntent)) return memoryIntent;
  memoryIntent = null;
  return null;
}

export function checkoutIdempotencyKey(intent: CheckoutIntent): string {
  const intentFingerprint = fingerprint(intent);
  const existing = readStoredIntent();
  if (existing?.fingerprint === intentFingerprint) return existing.key;

  const next: StoredIntent = {
    fingerprint: intentFingerprint,
    key: customerIdempotencyKey(),
    createdAt: Date.now(),
  };
  memoryIntent = next;
  const store = storage();
  if (store) {
    try {
      store.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // The in-memory copy still protects retries for the current WebView session.
    }
  }
  return next.key;
}

export function clearCheckoutIdempotencyKey(intent: CheckoutIntent, key: string): void {
  const existing = readStoredIntent();
  if (!existing) return;
  if (existing.fingerprint !== fingerprint(intent) || existing.key !== key) return;
  removeStoredIntent(storage());
}
