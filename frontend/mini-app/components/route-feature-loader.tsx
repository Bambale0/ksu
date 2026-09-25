"use client";

import { lazy, Suspense, useEffect, useState } from "react";

const FeedRouteFeatures = lazy(() => import("./feed-route-features"));
const CatalogRouteFeatures = lazy(() => import("./catalog-route-features"));

type RouteName = string | null;

function readRoute(): RouteName {
  if (typeof window === "undefined") return null;
  try {
    return new URL(window.location.href).searchParams.get("route") || "home";
  } catch {
    return "home";
  }
}

export function RouteFeatureLoader() {
  const [route, setRoute] = useState<RouteName>(null);

  useEffect(() => {
    const syncRoute = () => setRoute(readRoute());
    syncRoute();
    window.addEventListener("popstate", syncRoute);
    window.addEventListener("hashchange", syncRoute);
    return () => {
      window.removeEventListener("popstate", syncRoute);
      window.removeEventListener("hashchange", syncRoute);
    };
  }, []);

  if (route === null) return null;

  return (
    <Suspense fallback={null}>
      {route === "feed" ? <FeedRouteFeatures /> : null}
      {route === "home" || route === "catalog" ? <CatalogRouteFeatures /> : null}
    </Suspense>
  );
}
