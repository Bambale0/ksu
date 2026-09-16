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

export function userSafeHttpError(status: number, payload: unknown): Error {
  if (status >= 500) return new Error("Сервис временно недоступен. Попробуйте ещё раз.");
  if (status === 429) return new Error("Слишком много запросов. Попробуйте чуть позже.");
  if (status === 401) return new Error("Сессия истекла. Откройте ROXY заново.");
  if (status === 403) return new Error("Недостаточно прав для этого действия.");
  if (status === 404) return new Error("Данные не найдены или больше недоступны.");
  if (status === 422) return new Error("Проверьте введённые данные и попробуйте ещё раз.");

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
