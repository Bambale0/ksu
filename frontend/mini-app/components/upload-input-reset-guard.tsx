"use client";

import { useEffect } from "react";

function isFileInput(target: EventTarget | null): target is HTMLInputElement {
  return target instanceof HTMLInputElement && target.type === "file";
}

export function UploadInputResetGuard() {
  useEffect(() => {
    const resetAfterSelection = (event: Event) => {
      if (!isFileInput(event.target)) return;
      const input = event.target;
      window.setTimeout(() => {
        input.value = "";
      }, 0);
    };

    document.addEventListener("change", resetAfterSelection, false);
    return () => document.removeEventListener("change", resetAfterSelection, false);
  }, []);

  return null;
}
