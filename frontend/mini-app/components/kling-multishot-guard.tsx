"use client";

import { useEffect } from "react";

function setNativeTextareaValue(textarea: HTMLTextAreaElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
  setter?.call(textarea, value);
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
  textarea.dispatchEvent(new Event("change", { bubbles: true }));
}

function labelText(element: Element | null | undefined): string {
  return element?.textContent?.replace(/\s+\*$/, "").trim() || "";
}

function isScenesLabel(value: string): boolean {
  return value === "Кадры по сценам" || value === "Кадры multi-shot";
}

function bindScreen(screen: HTMLElement) {
  const toggle = Array.from(screen.querySelectorAll<HTMLInputElement>(".toggle-row input[type='checkbox']"))
    .find((input) => labelText(input.closest(".toggle-row")?.querySelector("strong")) === "Multi-shot");
  if (!toggle) return;

  const scenes = Array.from(screen.querySelectorAll<HTMLElement>(".field"))
    .find((field) => isScenesLabel(labelText(field.querySelector(".label"))));
  if (!scenes) return;

  const raw = scenes.querySelector<HTMLTextAreaElement>("textarea.control");
  const sync = () => {
    const enabled = toggle.checked;
    scenes.hidden = !enabled;
    scenes.setAttribute("aria-hidden", enabled ? "false" : "true");
    if (!enabled && raw && raw.value.trim() && raw.value.trim() !== "[]") {
      setNativeTextareaValue(raw, "[]");
    }
  };

  sync();
  if (toggle.dataset.klingMultishotBound === "true") return;
  toggle.dataset.klingMultishotBound = "true";
  toggle.addEventListener("change", sync);
}

export function KlingMultishotGuard() {
  useEffect(() => {
    const sync = () => {
      for (const screen of Array.from(document.querySelectorAll<HTMLElement>(".main-shell .screen"))) {
        bindScreen(screen);
      }
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return null;
}
