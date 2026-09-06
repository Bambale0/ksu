import { api } from "@/lib/api";

export async function resolveAdminAccess(attempts = 4): Promise<boolean> {
  const total = Math.max(1, attempts);
  for (let attempt = 0; attempt < total; attempt += 1) {
    try {
      const me = await api.me();
      return Boolean(me.is_admin);
    } catch {
      if (attempt + 1 >= total) return false;
      await new Promise((resolve) => window.setTimeout(resolve, 180 * (attempt + 1)));
    }
  }
  return false;
}
