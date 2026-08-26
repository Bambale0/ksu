import { AppEntryGate } from "@/components/app-entry-gate";
import { BalanceAnchorGuard } from "@/components/balance-anchor-guard";
import { CatalogFeatureHub } from "@/components/catalog-feature-hub";
import { CatalogParityFeatures } from "@/components/catalog-parity-features";
import { CustomerParityHub } from "@/components/customer-parity-hub";
import { GenerationQuantityControl } from "@/components/generation-quantity-control";
import { GlobalUxEnhancers } from "@/components/global-ux-enhancers";
import { KlingMultishotGuard } from "@/components/kling-multishot-guard";
import { PostPublishSharePrompt } from "@/components/post-publish-share-prompt";
import { SingleFeedSurfaceGuard } from "@/components/single-feed-surface-guard";
import { UniversalBackButton } from "@/components/universal-back-button";
import { UploadInputResetGuard } from "@/components/upload-input-reset-guard";
import { WalletParity } from "@/components/wallet-parity";
import { ReferenceMemoryProvider } from "@/lib/reference-memory";

export default function Page() {
  return (
    <ReferenceMemoryProvider>
      <UniversalBackButton />
      <SingleFeedSurfaceGuard />
      <AppEntryGate />
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
    </ReferenceMemoryProvider>
  );
}
