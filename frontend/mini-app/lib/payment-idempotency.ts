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

function readStoredIntent(): StoredIntent | null {
  const store = storage();
  if (!store) return null;
  try {
    const parsed = JSON.parse(store.getItem(STORAGE_KEY) || "null") as Partial<StoredIntent> | null;
    if (
      !parsed
      || typeof parsed.fingerprint !== "string"
      || typeof parsed.key !== "string"
      || typeof parsed.createdAt !== "number"
      || Date.now() - parsed.createdAt > INTENT_TTL_MS
    ) {
      store.removeItem(STORAGE_KEY);
      return null;
    }
    return parsed as StoredIntent;
  } catch {
    store.removeItem(STORAGE_KEY);
    return null;
  }
}

export function checkoutIdempotencyKey(intent: CheckoutIntent): string {
  const intentFingerprint = fingerprint(intent);
  const existing = readStoredIntent();
  if (existing?.fingerprint === intentFingerprint) return existing.key;

  const key = customerIdempotencyKey();
  storage()?.setItem(STORAGE_KEY, JSON.stringify({
    fingerprint: intentFingerprint,
    key,
    createdAt: Date.now(),
  } satisfies StoredIntent));
  return key;
}

export function clearCheckoutIdempotencyKey(intent: CheckoutIntent, key: string): void {
  const existing = readStoredIntent();
  if (!existing) return;
  if (existing.fingerprint !== fingerprint(intent) || existing.key !== key) return;
  storage()?.removeItem(STORAGE_KEY);
}
