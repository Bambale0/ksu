"use client";

import { useEffect } from "react";

import { reportClientError } from "@/lib/client-error-reporting";

export function ClientErrorReporter() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      reportClientError("window_error", event.error || event.message || "Window error");
    };
    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      reportClientError("unhandled_rejection", event.reason || "Unhandled promise rejection");
    };

    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onUnhandledRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
    };
  }, []);

  return null;
}
