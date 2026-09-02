"use client";

import { useEffect } from "react";

function legacyCopy(text: string): boolean {
  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    const copied = document.execCommand("copy");
    textarea.remove();
    return copied;
  } catch {
    return false;
  }
}

export function ClipboardCompatibilityBridge() {
  useEffect(() => {
    const clipboard = navigator.clipboard;
    const nativeWrite = clipboard?.writeText?.bind(clipboard);
    if (!clipboard || !nativeWrite) return;

    const writeText = async (text: string) => {
      try {
        await nativeWrite(text);
      } catch (error) {
        // iOS/Telegram WebViews can expose Clipboard API but reject writeText.
        // Keep the user gesture alive and fall back to the legacy copy path.
        if (!legacyCopy(text)) throw error;
      }
    };

    try {
      Object.defineProperty(clipboard, "writeText", {
        configurable: true,
        value: writeText,
      });
    } catch {
      try { clipboard.writeText = writeText; } catch { /* immutable WebView API */ }
    }

    return () => {
      try {
        Object.defineProperty(clipboard, "writeText", {
          configurable: true,
          value: nativeWrite,
        });
      } catch {
        try { clipboard.writeText = nativeWrite; } catch { /* immutable WebView API */ }
      }
    };
  }, []);

  return null;
}
