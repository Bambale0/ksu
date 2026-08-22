import { CatalogCapabilities } from "@/components/catalog-capabilities";
import { GenerationActionGate } from "@/components/generation-action-app";
import { GlobalUxEnhancers } from "@/components/global-ux-enhancers";
import { UniversalBackButton } from "@/components/universal-back-button";
import { ReferenceMemoryProvider } from "@/lib/reference-memory";

export default function Page() {
  return (
    <ReferenceMemoryProvider>
      <UniversalBackButton />
      <GenerationActionGate />
      <CatalogCapabilities />
      <GlobalUxEnhancers />
    </ReferenceMemoryProvider>
  );
}
