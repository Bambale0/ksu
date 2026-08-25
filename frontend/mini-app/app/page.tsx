import { AppEntryGate } from "@/components/app-entry-gate";
import { CatalogFeatureHub } from "@/components/catalog-feature-hub";
import { GenerationQuantityControl } from "@/components/generation-quantity-control";
import { GlobalUxEnhancers } from "@/components/global-ux-enhancers";
import { KlingMultishotGuard } from "@/components/kling-multishot-guard";
import { PostPublishSharePrompt } from "@/components/post-publish-share-prompt";
import { SingleFeedSurfaceGuard } from "@/components/single-feed-surface-guard";
import { UniversalBackButton } from "@/components/universal-back-button";
import { UploadInputResetGuard } from "@/components/upload-input-reset-guard";
import { ReferenceMemoryProvider } from "@/lib/reference-memory";

export default function Page() {
  return (
    <ReferenceMemoryProvider>
      <UniversalBackButton />
      <SingleFeedSurfaceGuard />
      <AppEntryGate />
      <CatalogFeatureHub />
      <GenerationQuantityControl />
      <UploadInputResetGuard />
      <PostPublishSharePrompt />
      <GlobalUxEnhancers />
      <KlingMultishotGuard />
    </ReferenceMemoryProvider>
  );
}
