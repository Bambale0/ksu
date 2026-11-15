"use client";

import { useEffect } from "react";

import { reportClientError } from "@/lib/client-error-reporting";
import { attemptChunkReload, isChunkLoadFailure } from "@/lib/chunk-recovery";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    reportClientError("react_error", error, { digest: error.digest || null });
    try {
      attemptChunkReload(error, window.sessionStorage, () => window.location.reload());
    } catch {
      // Keep the error boundary usable if the embedded browser denies storage.
    }
  }, [error]);

  return (
    <main className="splash" role="alert">
      <strong>ROXY</strong>
      <small>Не удалось открыть приложение. Ошибка уже отправлена в диагностику.</small>
      <button
        type="button"
        className="primary-button"
        onClick={() => {
          if (isChunkLoadFailure(error)) {
            window.location.reload();
          } else {
            reset();
          }
        }}
      >
        {isChunkLoadFailure(error) ? "Обновить приложение" : "Попробовать снова"}
      </button>
    </main>
  );
}
