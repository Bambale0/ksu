"use client";

import type { TrendItem } from "@/lib/types";
import { GlobalUxEnhancers } from "./global-ux-enhancers";

export default function InteractiveRouteEnhancers({ trends }: { trends: TrendItem[] }) {
  return <GlobalUxEnhancers trends={trends} />;
}
