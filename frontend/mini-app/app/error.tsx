"use client";

import { useEffect } from "react";

import { reportClientError } from "@/lib/client-error-reporting";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    reportClientError("react_error", error, { digest: error.digest || null });
  }, [error]);

  return (
    <main className="splash" role="alert">
      <strong>ROXY</strong>
      <small>Не удалось открыть приложение. Ошибка уже отправлена в диагностику.</small>
      <button type="button" className="primary-button" onClick={reset}>
        Попробовать снова
      </button>
    </main>
  );
}
