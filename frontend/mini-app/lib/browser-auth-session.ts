const BROWSER_AUTH_STORAGE_KEY = "__roxy_browser_init_data_v1";
const DEFAULT_BROWSER_AUTH_TTL_SECONDS = 24 * 60 * 60;

type StoredBrowserAuth = {
  initData: string;
  expiresAt: number;
};

export function saveBrowserInitData(initData: string, expiresIn: number): void {
  if (typeof window === "undefined") return;
  const value = String(initData || "").trim();
  if (!value) return;
  const ttlSeconds = Number.isFinite(expiresIn) && expiresIn > 0
    ? expiresIn
    : DEFAULT_BROWSER_AUTH_TTL_SECONDS;
  try {
    const stored: StoredBrowserAuth = {
      initData: value,
      expiresAt: Date.now() + ttlSeconds * 1000,
    };
    window.sessionStorage.setItem(BROWSER_AUTH_STORAGE_KEY, JSON.stringify(stored));
  } catch {
    // Restrictive browsers can disable sessionStorage. The login gate will be
    // shown again after reload rather than weakening the auth boundary.
  }
}

export function getBrowserInitData(): string {
  if (typeof window === "undefined") return "";
  try {
    const raw = window.sessionStorage.getItem(BROWSER_AUTH_STORAGE_KEY);
    if (!raw) return "";
    const stored = JSON.parse(raw) as Partial<StoredBrowserAuth> | null;
    const initData = String(stored?.initData || "").trim();
    const expiresAt = Number(stored?.expiresAt || 0);
    if (!initData || !Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
      window.sessionStorage.removeItem(BROWSER_AUTH_STORAGE_KEY);
      return "";
    }
    return initData;
  } catch {
    try { window.sessionStorage.removeItem(BROWSER_AUTH_STORAGE_KEY); } catch { /* unavailable */ }
    return "";
  }
}
