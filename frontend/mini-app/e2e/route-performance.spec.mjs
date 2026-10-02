import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const source = (relativePath) => readFileSync(
  fileURLToPath(new URL(relativePath, import.meta.url)),
  "utf8",
);

test("root Mini App keeps route-heavy surfaces out of the eager startup graph", () => {
  const page = source("../app/page.tsx");
  const app = source("../components/roxy-social-app.tsx");

  expect(app).toContain('import { RouteFeatureLoader } from "./route-feature-loader";');
  expect(app).toMatch(/<RouteFeatureLoader\s+route=\{route\}[\s\S]*?\/>/);
  expect(page).not.toContain("RouteFeatureLoader");

  for (const eagerFeature of [
    "TikTokFeedSurface",
    "FeedResponsiveLayout",
    "FeedAdminModeration",
    "CatalogFeatureHub",
    "LiveTrendRail",
    "HomeTrendFolders",
    "CatalogTrendFolders",
    "CatalogParityFeatures",
  ]) {
    expect(page).not.toContain(`import { ${eagerFeature} }`);
    expect(page).not.toContain(`<${eagerFeature} />`);
  }
});

test("route loader code-splits feed and catalog feature groups", () => {
  const loader = source("../components/route-feature-loader.tsx");

  expect(loader).toContain('lazy(() => import("./feed-route-features"))');
  expect(loader).toContain('lazy(() => import("./catalog-route-features"))');
  expect(loader).toContain("type RouteFeatureLoaderProps");
  expect(loader).toContain("route: Route;");
});


test("canonical client navigation notifies route-scoped feature loading", () => {
  const app = source("../components/roxy-social-app.tsx");
  expect(app).toMatch(/window\.history\.pushState\([\s\S]{0,240}window\.dispatchEvent\(new Event\("popstate"\)\)/);
});

test("root bootstrap does not wait on unrelated feed, promo, or legacy onboarding requests", () => {
  const app = source("../components/roxy-social-app.tsx");
  const start = app.indexOf("const initial = initialRoute();");
  const end = app.indexOf("})();", start);
  expect(start).toBeGreaterThan(-1);
  expect(end).toBeGreaterThan(start);
  const bootstrap = app.slice(start, end);

  expect(bootstrap).not.toContain("api.feed(");
  expect(bootstrap).not.toContain('api.generations("limit=12")');
  expect(bootstrap).not.toContain("api.trends(");
  expect(bootstrap).not.toContain("api.activePromo(");
  expect(bootstrap).not.toContain("api.onboarding(");
  expect(app).toContain('route === "catalog" || (!booting && route === "home")');
  expect(app).not.toContain("<Onboarding data=");
});

test("route-only account and creation helpers stay out of the eager root graph", () => {
  const page = source("../app/page.tsx");
  const loader = source("../components/route-feature-loader.tsx");

  for (const eagerFeature of ["CustomerParityHub", "PartnerRoxTransfer", "GlobalUxEnhancers"]) {
    expect(page).not.toContain(`import { ${eagerFeature} }`);
    expect(page).not.toContain(`<${eagerFeature} />`);
  }

  expect(loader).toContain('lazy(() => import("./account-route-features"))');
  expect(loader).toContain('lazy(() => import("./interactive-route-enhancers"))');
});

test("wallet provider discovery waits until a wallet package sheet actually exists", () => {
  const page = source("../app/page.tsx");
  const loader = source("../components/wallet-parity-loader.tsx");

  expect(page).not.toContain('import { WalletParity } from "@/components/wallet-parity";');
  expect(page).toContain('import { WalletParityLoader } from "@/components/wallet-parity-loader";');
    expect(loader).toMatch(/lazy\(\(\) =>\s*import\("\.\/wallet-parity"\)/);
  expect(loader).toContain('.sheet .package-grid');
});
