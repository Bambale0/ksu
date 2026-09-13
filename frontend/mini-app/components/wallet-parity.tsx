"use client";

import { createPortal } from "react-dom";
import { useEffect, useState } from "react";

import { customerRequest } from "@/lib/customer-api";

type PackageCatalog = {
  configured?: boolean;
  packages: Record<string, unknown>;
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
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [lavaAvailable, setLavaAvailable] = useState(false);
  const [cryptoBotAvailable, setCryptoBotAvailable] = useState(false);

  useEffect(() => {
    void Promise.allSettled([
      customerRequest<PackageCatalog>("/api/v1/payments/card/packages"),
      customerRequest<PackageCatalog>("/api/v1/payments/crypto/packages"),
    ]).then(([lava, cryptoBot]) => {
      setLavaAvailable(Boolean(
        lava.status === "fulfilled"
        && lava.value.configured
        && Object.keys(lava.value.packages || {}).length,
      ));
      setCryptoBotAvailable(Boolean(
        cryptoBot.status === "fulfilled"
        && cryptoBot.value.configured
        && Object.keys(cryptoBot.value.packages || {}).length,
      ));
    });
  }, []);

  useEffect(() => {
    let frame = 0;
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const sheet = document.querySelector<HTMLElement>(".sheet");
        setHost(sheet ? ensureHost(sheet) : null);
      });
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

  if (!host) return null;
  return createPortal(
    <div className="wallet-parity-link">
      <button className="secondary wide" type="button" onClick={() => window.location.assign("/mini-app/promocodes/")}>Есть промокод?</button>
      {lavaAvailable ? <button className="secondary wide" type="button" onClick={() => window.location.assign("/mini-app/payments/?provider=card")}>Резервная оплата · Lava Top</button> : null}
      {cryptoBotAvailable ? <button className="secondary wide" type="button" onClick={() => window.location.assign("/mini-app/payments/?provider=cryptobot")}>Оплатить криптой · CryptoBot</button> : null}
      <small>ЮKassa остаётся основным способом. Пакет начисляет ровно указанное количество ROX. Lava Top — резерв для карты, CryptoBot — для криптовалюты. Бонусные ROX доступны только по промокоду и только после успешной оплаты.</small>
    </div>,
    host,
  );
}
