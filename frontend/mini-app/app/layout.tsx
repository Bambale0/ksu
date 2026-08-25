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
import "./services.css";
import "./suno-audio.css";
import "./feed-social.css";

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
        {telegramSdkEnabled ? <Script src="https://telegram.org/js/telegram-web-app.js?63" strategy="beforeInteractive" /> : null}
        <Script id="roxy-draft-schema-reset" strategy="beforeInteractive">{draftSchemaReset}</Script>
        <Script src="/mini-app/publish-privacy.js" strategy="afterInteractive" />
        <Script src="/mini-app/rox-price-only.js" strategy="afterInteractive" />
        <Script src="/mini-app/keyboard-reference-ux.js" strategy="afterInteractive" />
        <Script src="/mini-app/feed-social-polish.js" strategy="afterInteractive" />
        {children}
      </body>
    </html>
  );
}
