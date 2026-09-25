"use client";

import { lazy, Suspense, useEffect, useState } from "react";

const WalletParity = lazy(() =>
  import("./wallet-parity").then((module) => ({ default: module.WalletParity })),
);

export function WalletParityLoader() {
  const [needed, setNeeded] = useState(false);

  useEffect(() => {
    if (needed) return;
    const sync = () => {
      if (document.querySelector(".sheet .package-grid")) setNeeded(true);
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [needed]);

  if (!needed) return null;
  return <Suspense fallback={null}><WalletParity /></Suspense>;
}
