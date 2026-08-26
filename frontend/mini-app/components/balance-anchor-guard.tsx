"use client";

import { useEffect } from "react";

export function BalanceAnchorGuard() {
  useEffect(() => {
    const sync = () => {
      const button = document.querySelector<HTMLButtonElement>("button.balance-button");
      if (button && button.id !== "balance") button.id = "balance";
    };

    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return null;
}
