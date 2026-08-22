import { CatalogCapabilities } from "@/components/catalog-capabilities";
import { GenerationActionGate } from "@/components/generation-action-app";
import { ReferenceMemoryProvider } from "@/lib/reference-memory";

export default function Page() {
  return (
    <ReferenceMemoryProvider>
      <GenerationActionGate />
      <CatalogCapabilities />
    </ReferenceMemoryProvider>
  );
}