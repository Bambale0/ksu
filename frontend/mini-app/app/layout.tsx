import type { Metadata, Viewport } from "next";
import Script from "next/script";
import type { ReactNode } from "react";
import "./globals.css";
import "./loader.css";
import "./catalog.css";
import "./ux-polish.css";
import "./preview-polish.css";
import "./wallet-bonuses.css";
import "./reference-memory.css";
import "./generation-actions.css";
import "./keyboard-ux.css";
import "./standalone-tools.css";
import "./action-polish.css";
import "./responsive.css";

export const metadata: Metadata = {
  title: "ROXY · AI Creative Studio",
  description: "ROXY AI Creative Studio",
  applicationName: "ROXY",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#0B0B10",
  colorScheme: "dark",
};

const launchSnapshot = `
(() => {
  try {
    const snapshot = { hash: window.location.hash || "", search: window.location.search || "" };
    window.__ROXY_INITIAL_LAUNCH__ = snapshot;

    const routingOnly = (raw) => {
      const source = new URLSearchParams(String(raw || "").replace(/^[?#]/, ""));
      const safe = new URLSearchParams();
      for (const name of ["tgWebAppStartParam", "start_payload", "startapp", "start", "ref"]) {
        const value = source.get(name);
        if (value) safe.set(name, value);
      }
      return safe.toString();
    };

    // Keep Telegram auth initData in page memory only. Session storage receives
    // only non-secret routing payloads needed after client-side navigation.
    window.sessionStorage?.setItem("__roxy_initial_hash", routingOnly(snapshot.hash));
    window.sessionStorage?.setItem("__roxy_initial_search", routingOnly(snapshot.search));
  } catch {}
})();
`;

const draftSchemaReset = `
(() => {
  try {
    const versionKey = "roxy.next.generation-drafts.schema";
    const currentVersion = "4";
    if (window.localStorage?.getItem(versionKey) !== currentVersion) {
      window.localStorage?.removeItem("roxy.next.generation-drafts.v3");
      window.localStorage?.setItem(versionKey, currentVersion);
    }
  } catch {}
})();
`;

const telegramSdkEnabled = process.env.ROXY_E2E !== "1";

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ru">
      <body>
        <Script id="roxy-launch-snapshot" strategy="beforeInteractive">{launchSnapshot}</Script>
        {telegramSdkEnabled ? <Script src="https://telegram.org/js/telegram-web-app.js?63" strategy="beforeInteractive" /> : null}
        <Script id="roxy-draft-schema-reset" strategy="beforeInteractive">{draftSchemaReset}</Script>
        <Script src="/mini-app/publish-privacy.js" strategy="afterInteractive" />
        <Script src="/mini-app/rox-price-only.js" strategy="afterInteractive" />
        <Script src="/mini-app/keyboard-reference-ux.js" strategy="afterInteractive" />
        {children}
      </body>
    </html>
  );
}
