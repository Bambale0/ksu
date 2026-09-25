"use client";

import { FeedAdminModeration } from "./feed-admin-moderation";
import { FeedResponsiveLayout } from "./feed-responsive-layout";
import { TikTokFeedSurface } from "./tiktok-feed-surface";

export default function FeedRouteFeatures() {
  return (
    <>
      <TikTokFeedSurface />
      <FeedResponsiveLayout />
      <FeedAdminModeration />
    </>
  );
}
