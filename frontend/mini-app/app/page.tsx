import { AppEntryGate } from "@/components/app-entry-gate";
import { CatalogCapabilities } from "@/components/catalog-capabilities";
import { CatalogTrendLaunch } from "@/components/catalog-trend-launch";
import { GenerationQuantityControl } from "@/components/generation-quantity-control";
import { GlobalUxEnhancers } from "@/components/global-ux-enhancers";
import { KlingMultishotGuard } from "@/components/kling-multishot-guard";
import { PostPublishSharePrompt } from "@/components/post-publish-share-prompt";
import { ServicesLauncher } from "@/components/services-launcher";
import { UniversalBackButton } from "@/components/universal-back-button";
import { UploadInputResetGuard } from "@/components/upload-input-reset-guard";
import { ReferenceMemoryProvider } from "@/lib/reference-memory";

export default function Page() {
  return (
    <ReferenceMemoryProvider>
      <UniversalBackButton />
      <AppEntryGate />
      <ServicesLauncher />
      <CatalogCapabilities />
      <CatalogTrendLaunch />
      <GenerationQuantityControl />
      <UploadInputResetGuard />
      <PostPublishSharePrompt />
      <GlobalUxEnhancers />
      <KlingMultishotGuard />
    </ReferenceMemoryProvider>
  );
}
