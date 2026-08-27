import { AppEntryGate } from "@/components/app-entry-gate";
import { BalanceAnchorGuard } from "@/components/balance-anchor-guard";
import { CatalogFeatureHub } from "@/components/catalog-feature-hub";
import { CatalogParityFeatures } from "@/components/catalog-parity-features";
import { ClientErrorReporter } from "@/components/client-error-reporter";
import { CustomerParityHub } from "@/components/customer-parity-hub";
import { GenerationQuantityControl } from "@/components/generation-quantity-control";
import { GlobalUxEnhancers } from "@/components/global-ux-enhancers";
import { InlineTrendAdmin } from "@/components/inline-trend-admin";
import { KlingMultishotGuard } from "@/components/kling-multishot-guard";
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
      <BalanceAnchorGuard />
      <CatalogFeatureHub />
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
