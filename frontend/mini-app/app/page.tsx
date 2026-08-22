import { CatalogCapabilities } from "@/components/catalog-capabilities";
import { GenerationActionGate } from "@/components/generation-action-app";
import { UniversalBackButton } from "@/components/universal-back-button";
import { ReferenceMemoryProvider } from "@/lib/reference-memory";

export default function Page() {
  return (
    <ReferenceMemoryProvider>
      <UniversalBackButton />
      <GenerationActionGate />
      <CatalogCapabilities />
    </ReferenceMemoryProvider>
  );
}
