"use client";

import type { TrendItem } from "@/lib/types";

import { AiReferenceHomeEntry } from "./ai-reference-home-entry";
import { CatalogFeatureHub } from "./catalog-feature-hub";
import { CatalogParityFeatures } from "./catalog-parity-features";
import { CatalogTrendFolders } from "./catalog-trend-folders";
import { HomeTrendFolders } from "./home-trend-folders";
import { LiveTrendRail } from "./live-trend-rail";

type CatalogRouteFeaturesProps = {
  trends: TrendItem[];
  isAdmin: boolean;
  trendError: string;
  onTrendDeleted: (trendId: string) => void;
  onRetryTrends: () => void | Promise<TrendItem[]>;
};

export default function CatalogRouteFeatures(props: CatalogRouteFeaturesProps) {
  return (
    <>
      <CatalogFeatureHub />
      <LiveTrendRail {...props} />
      <HomeTrendFolders />
      <AiReferenceHomeEntry />
      <CatalogTrendFolders />
      <CatalogParityFeatures />
    </>
  );
}
