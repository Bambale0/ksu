type ErrorPayload = {
  detail?: unknown;
  message?: unknown;
};

function textDetail(value: unknown): string | null {
  if (typeof value === "string") {
    const text = value.trim();
    return text || null;
  }
  if (value && typeof value === "object" && "message" in value) {
    const message = (value as { message?: unknown }).message;
    return typeof message === "string" && message.trim() ? message.trim() : null;
  }
  return null;
}

function validationDetail(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const detail = textDetail((payload as ErrorPayload).detail);
  if (!detail || detail.length > 320 || /[\r\n]/.test(detail)) return null;
  if (/\b(traceback|stack trace|exception|internal server error)\b/i.test(detail)) return null;
  return detail;
}

export function userSafeHttpError(status: number, payload: unknown): Error {
  if (status >= 500) return new Error("Сервис временно недоступен. Попробуйте ещё раз.");
  if (status === 429) return new Error("Слишком много запросов. Попробуйте чуть позже.");
  if (status === 401) return new Error("Сессия истекла. Откройте ROXY заново.");
  if (status === 403) return new Error("Недостаточно прав для этого действия.");
  if (status === 404) return new Error("Данные не найдены или больше недоступны.");
  if (status === 422) {
    const detail = validationDetail(payload);
    return new Error(detail || "Проверьте введённые данные и попробуйте ещё раз.");
  }

  const body = payload && typeof payload === "object" ? payload as ErrorPayload : {};
  const detail = textDetail(body.detail) || textDetail(body.message);
  if (detail) return new Error(detail);
  return new Error("Не удалось выполнить действие. Попробуйте ещё раз.");
}

export function userSafeNetworkError(reason: unknown): Error {
  if (reason instanceof DOMException && reason.name === "AbortError") {
    return new Error("Запрос был отменён. Попробуйте ещё раз.");
  }
  return new Error("Не удалось связаться с сервером. Проверьте интернет и попробуйте ещё раз.");
}

export const CLIENT_REQUEST_TIMEOUT_MS = 20_000;

async function withRequestDeadline<T>(
  init: RequestInit,
  timeoutMs: number,
  operation: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  const controller = new AbortController();
  const upstream = init.signal;
  let timedOut = false;

  const abortFromUpstream = () => controller.abort();
  if (upstream?.aborted) {
    controller.abort();
  } else {
    upstream?.addEventListener("abort", abortFromUpstream, { once: true });
  }

  const timer = globalThis.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    return await operation(controller.signal);
  } catch (reason) {
    if (timedOut) throw new Error("Сервер отвечает слишком долго. Попробуйте ещё раз.");
    throw userSafeNetworkError(reason);
  } finally {
    globalThis.clearTimeout(timer);
    upstream?.removeEventListener("abort", abortFromUpstream);
  }
}

export async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs = CLIENT_REQUEST_TIMEOUT_MS,
): Promise<Response> {
  return withRequestDeadline(init, timeoutMs, async (signal) => {
    const response = await fetch(input, { ...init, signal });
    // fetch() resolves after headers. Drain a clone before returning so the
    // deadline also covers a server/proxy that stalls the response body. The
    // original Response remains untouched for callers to parse normally.
    if (response.status !== 204 && response.body) await response.clone().arrayBuffer();
    return response;
  });
}
