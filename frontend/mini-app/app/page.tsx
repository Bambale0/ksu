import { AppEntryGate } from "@/components/app-entry-gate";
import { CatalogCapabilities } from "@/components/catalog-capabilities";
import { CatalogTrendLaunch } from "@/components/catalog-trend-launch";
import { GlobalUxEnhancers } from "@/components/global-ux-enhancers";
import { KlingMultishotGuard } from "@/components/kling-multishot-guard";
import { UniversalBackButton } from "@/components/universal-back-button";
import { ReferenceMemoryProvider } from "@/lib/reference-memory";

export default function Page() {
  return (
    <ReferenceMemoryProvider>
      <UniversalBackButton />
      <AppEntryGate />
      <CatalogCapabilities />
      <CatalogTrendLaunch />
      <GlobalUxEnhancers />
      <KlingMultishotGuard />
    </ReferenceMemoryProvider>
  );
}
