"use client";

import { createPortal } from "react-dom";
import { useEffect, useMemo, useState } from "react";

import { compactNumber, customerRequest } from "@/lib/customer-api";

type Package = {
  credits: string;
  bonus_credits?: string;
  total_credits?: string;
  prices: Record<string, string>;
};
type PackageCatalog = {
  packages: Record<string, Package>;
};

function ensureHost(sheet: HTMLElement): HTMLElement {
  const existing = sheet.querySelector<HTMLElement>("[data-wallet-parity-host]");
  if (existing) return existing;
  const host = document.createElement("div");
  host.dataset.walletParityHost = "true";
  const grid = sheet.querySelector(".package-grid");
  if (grid?.nextSibling) sheet.insertBefore(host, grid.nextSibling);
  else sheet.appendChild(host);
  return host;
}

export function WalletParity() {
  const [catalog, setCatalog] = useState<PackageCatalog | null>(null);
  const [host, setHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    void customerRequest<PackageCatalog>("/api/v1/payments/card/packages")
      .then(setCatalog)
      .catch(() => setCatalog(null));
  }, []);

  const packages = useMemo(() => Object.values(catalog?.packages || {}), [catalog]);

  useEffect(() => {
    let frame = 0;
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const sheet = document.querySelector<HTMLElement>(".sheet");
        setHost(sheet ? ensureHost(sheet) : null);
        if (!sheet || !packages.length) return;
        const buttons = Array.from(sheet.querySelectorAll<HTMLElement>(".package-grid .package"));
        buttons.forEach((button, index) => {
          const existing = button.querySelector<HTMLElement>(".package-bonus-live");
          const item = packages[index];
          const bonus = Number(item?.bonus_credits || 0);
          if (!item || !(bonus > 0)) {
            existing?.remove();
            return;
          }
          const text = `+${compactNumber(bonus)} ROX 🎁`;
          if (existing) {
            if (existing.textContent !== text) existing.textContent = text;
            return;
          }
          const badge = document.createElement("span");
          badge.className = "package-bonus-live";
          badge.textContent = text;
          button.appendChild(badge);
        });
      });
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, [packages]);

  if (!host) return null;
  return createPortal(
    <div className="wallet-parity-link">
      <button className="secondary wide" type="button" onClick={() => window.location.assign("/mini-app/payments/")}>Все пополнения и статусы</button>
      <small>Бонусы и итоговые ROX берутся из текущих настроек оплаты.</small>
    </div>,
    host,
  );
}
