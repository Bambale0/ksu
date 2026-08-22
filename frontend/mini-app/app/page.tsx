import { CatalogCapabilities } from "@/components/catalog-capabilities";
import { RoxySocialApp } from "@/components/roxy-social-app";
import { ReferenceMemoryProvider } from "@/lib/reference-memory";

export default function Page() {
  return (
    <ReferenceMemoryProvider>
      <RoxySocialApp />
      <CatalogCapabilities />
    </ReferenceMemoryProvider>
  );
}
