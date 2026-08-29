import { AppEntryGate } from "@/components/app-entry-gate";
import { BalanceAnchorGuard } from "@/components/balance-anchor-guard";
import { CatalogFeatureHub } from "@/components/catalog-feature-hub";
import { CatalogParityFeatures } from "@/components/catalog-parity-features";
import { ClientErrorReporter } from "@/components/client-error-reporter";
import { CustomerParityHub } from "@/components/customer-parity-hub";
import { FeedAdminModeration } from "@/components/feed-admin-moderation";
import { FeedResponsiveLayout } from "@/components/feed-responsive-layout";
import { GenerationQuantityControl } from "@/components/generation-quantity-control";
import { GlobalUxEnhancers } from "@/components/global-ux-enhancers";
import { InlineTrendAdmin } from "@/components/inline-trend-admin";
import { KlingMultishotGuard } from "@/components/kling-multishot-guard";
import { LiveTrendRail } from "@/components/live-trend-rail";
import { PostPublishSharePrompt } from "@/components/post-publish-share-prompt";
import { TikTokFeedSurface } from "@/components/tiktok-feed-surface";
import { UploadInputResetGuard } from "@/components/upload-input-reset-guard";
import { WalletParity } from "@/components/wallet-parity";
import { ReferenceMemoryProvider } from "@/lib/reference-memory";

export default function Page() {
  return (
    <ReferenceMemoryProvider>
      <ClientErrorReporter />
      <AppEntryGate />
      <TikTokFeedSurface />
      <FeedResponsiveLayout />
      <FeedAdminModeration />
      <BalanceAnchorGuard />
      <CatalogFeatureHub />
      <LiveTrendRail />
      <CatalogParityFeatures />
      <CustomerParityHub />
      <WalletParity />
      <GenerationQuantityControl />
      <UploadInputResetGuard />
      <PostPublishSharePrompt />
      <GlobalUxEnhancers />
      <KlingMultishotGuard />
      <InlineTrendAdmin />
    </ReferenceMemoryProvider>
  );
}
