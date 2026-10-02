"use client";

import { lazy, Suspense } from "react";
import type { Route, TrendItem } from "@/lib/types";

const FeedRouteFeatures = lazy(() => import("./feed-route-features"));
const CatalogRouteFeatures = lazy(() => import("./catalog-route-features"));
const AccountRouteFeatures = lazy(() => import("./account-route-features"));
const InteractiveRouteEnhancers = lazy(() => import("./interactive-route-enhancers"));

type RouteFeatureLoaderProps = {
  route: Route;
  trends: TrendItem[];
  isAdmin: boolean;
  trendError: string;
  onTrendDeleted: (trendId: string) => void;
  onRetryTrends: () => void | Promise<TrendItem[]>;
};

export function RouteFeatureLoader({
  route,
  trends,
  isAdmin,
  trendError,
  onTrendDeleted,
  onRetryTrends,
}: RouteFeatureLoaderProps) {
  const accountRoute = route === "profile" || route === "partners" || route === "history";
  const interactiveRoute = route === "home" || route === "catalog" || route === "create";

  return (
    <Suspense fallback={null}>
      {route === "feed" ? <FeedRouteFeatures /> : null}
      {route === "home" || route === "catalog" ? (
        <CatalogRouteFeatures
          trends={trends}
          isAdmin={isAdmin}
          trendError={trendError}
          onTrendDeleted={onTrendDeleted}
          onRetryTrends={onRetryTrends}
        />
      ) : null}
      {accountRoute ? <AccountRouteFeatures route={route} /> : null}
      {interactiveRoute ? <InteractiveRouteEnhancers trends={trends} /> : null}
    </Suspense>
  );
}
