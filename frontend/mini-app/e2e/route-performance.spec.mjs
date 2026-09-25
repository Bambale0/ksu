import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const source = (relativePath) => readFileSync(
  fileURLToPath(new URL(relativePath, import.meta.url)),
  "utf8",
);

test("root Mini App keeps route-heavy surfaces out of the eager startup graph", () => {
  const page = source("../app/page.tsx");

  expect(page).toContain('import { RouteFeatureLoader } from "@/components/route-feature-loader";');
  expect(page).toContain("<RouteFeatureLoader />");

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
  expect(loader).toContain('addEventListener("popstate"');
});
