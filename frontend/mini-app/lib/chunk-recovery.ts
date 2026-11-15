/**
 * Recover transient Next.js chunk-load failures without creating reload loops.
 * A full navigation is necessary for a missing JS module: React reset() alone
 * can reuse the old module manifest and fail the same lazy import again.
 */
const RELOAD_KEY = "roxy.chunk-recovery.last-reload";
const RELOAD_WINDOW_MS = 5 * 60 * 1000;

type StorageLike = Pick<Storage, "getItem" | "setItem">;

export function isChunkLoadFailure(error: { name?: string; message?: string } | null): boolean {
  const description = String(error?.name || "") + " " + String(error?.message || "");
  return /ChunkLoadError|Failed to load chunk|Loading chunk .* failed|Failed to fetch dynamically imported module/i.test(description);
}

export function attemptChunkReload(
  error: { name?: string; message?: string } | null,
  storage: StorageLike | null,
  reload: () => void,
  now: number = Date.now(),
): boolean {
  if (!isChunkLoadFailure(error) || !storage) return false;
  try {
    const lastRaw = storage.getItem(RELOAD_KEY);
    if (lastRaw !== null) {
      const previous = Number(lastRaw);
      if (Number.isFinite(previous) && now - previous >= 0 && now - previous < RELOAD_WINDOW_MS) {
        return false;
      }
    }
    // Record the attempt before reload so a missing deployment does not loop.
    storage.setItem(RELOAD_KEY, String(now));
  } catch {
    // If sessionStorage is blocked, leave recovery to the explicit user action.
    return false;
  }
  reload();
  return true;
}
