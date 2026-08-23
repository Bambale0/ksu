"use client";

import { useEffect } from "react";

const DASHES = /[\u2010\u2011\u2012\u2013\u2014\u2212]/g;

function normalizeWalletEmailInput(input: HTMLInputElement): void {
  if (input.type === "email") input.type = "text";
  if (input.inputMode !== "email") input.inputMode = "email";
  const normalized = input.value.replace(DASHES, "-");
  if (normalized !== input.value) {
    input.value = normalized;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
}

function normalizeAllWalletEmailInputs(root: ParentNode = document): void {
  root
    .querySelectorAll<HTMLInputElement>(".wallet-input[autocomplete='email'], input[autocomplete='email'][inputmode='email']")
    .forEach(normalizeWalletEmailInput);
}

export function WalletEmailInputGuard() {
  useEffect(() => {
    normalizeAllWalletEmailInputs();
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node instanceof HTMLInputElement) normalizeWalletEmailInput(node);
          if (node instanceof HTMLElement) normalizeAllWalletEmailInputs(node);
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("input", (event) => {
      if (event.target instanceof HTMLInputElement) normalizeWalletEmailInput(event.target);
    });
    return () => observer.disconnect();
  }, []);
  return null;
}
