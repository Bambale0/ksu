"use client";

import { AiReferenceHomeEntry } from "./ai-reference-home-entry";
import { CatalogFeatureHub } from "./catalog-feature-hub";
import { CatalogParityFeatures } from "./catalog-parity-features";
import { CatalogTrendFolders } from "./catalog-trend-folders";
import { HomeTrendFolders } from "./home-trend-folders";
import { LiveTrendRail } from "./live-trend-rail";

export default function CatalogRouteFeatures() {
  return (
    <>
      <CatalogFeatureHub />
      <LiveTrendRail />
      <HomeTrendFolders />
      <AiReferenceHomeEntry />
      <CatalogTrendFolders />
      <CatalogParityFeatures />
    </>
  );
}
