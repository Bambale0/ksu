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
  configured?: boolean;
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
  const [cryptoAvailable, setCryptoAvailable] = useState(false);

  useEffect(() => {
    void Promise.allSettled([
      customerRequest<PackageCatalog>("/api/v1/payments/card/packages"),
      customerRequest<PackageCatalog>("/api/v1/payments/crypto/packages"),
    ]).then(([card, crypto]) => {
      setCatalog(card.status === "fulfilled" ? card.value : null);
      setCryptoAvailable(Boolean(
        crypto.status === "fulfilled"
        && crypto.value.configured
        && Object.keys(crypto.value.packages || {}).length,
      ));
    });
  }, []);

  const packages = useMemo(() => catalog?.packages || {}, [catalog]);

  useEffect(() => {
    let frame = 0;
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const sheet = document.querySelector<HTMLElement>(".sheet");
        setHost(sheet ? ensureHost(sheet) : null);
        if (!sheet || !Object.keys(packages).length) return;
        const buttons = Array.from(sheet.querySelectorAll<HTMLElement>(".package-grid .package"));
        const packageList = Object.values(packages);
        buttons.forEach((button, index) => {
          const existing = button.querySelector<HTMLElement>(".package-bonus-live");
          const packageId = String(button.dataset.packageId || "");
          const item = packageId ? packages[packageId] : packageList[index];
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
      {cryptoAvailable ? <button className="primary wide" type="button" onClick={() => window.location.assign("/mini-app/payments/?provider=2328")}>Оплатить криптовалютой</button> : null}
      <button className="secondary wide" type="button" onClick={() => window.location.assign("/mini-app/payments/")}>Все пополнения и статусы</button>
      <small>Карта/СБП и криптовалюта используют серверные пакеты и бонусы ROX.</small>
    </div>,
    host,
  );
}
