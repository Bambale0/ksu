import { AppEntryGate } from "@/components/app-entry-gate";
import { BalanceAnchorGuard } from "@/components/balance-anchor-guard";
import { ClientErrorReporter } from "@/components/client-error-reporter";
import { CustomerParityHub } from "@/components/customer-parity-hub";
import { GenerationQuantityControl } from "@/components/generation-quantity-control";
import { GenerationQuoteFreshnessGuard } from "@/components/generation-quote-freshness-guard";
import { GenerationSubmitGuard } from "@/components/generation-submit-guard";
import { GlobalUxEnhancers } from "@/components/global-ux-enhancers";
import { HistoryPromptCopyUx } from "@/components/history-prompt-copy-ux";
import { InlineTrendAdmin } from "@/components/inline-trend-admin";
import { KlingMultishotGuard } from "@/components/kling-multishot-guard";
import { PartnerRoxTransfer } from "@/components/partner-rox-transfer";
import { PostPublishSharePrompt } from "@/components/post-publish-share-prompt";
import { PrivateRepeatLinkUx } from "@/components/private-repeat-link-ux";
import { RouteFeatureLoader } from "@/components/route-feature-loader";
import { UnpublishFeedbackGuard } from "@/components/unpublish-feedback-guard";
import { UploadInputResetGuard } from "@/components/upload-input-reset-guard";
import { UserOnboardingGate } from "@/components/user-onboarding";
import { WalletEmailInputGuard } from "@/components/wallet-email-input-guard";
import { WalletParity } from "@/components/wallet-parity";
import { ReferenceMemoryProvider } from "@/lib/reference-memory";

export default function Page() {
  return (
    <ReferenceMemoryProvider>
      <ClientErrorReporter />
      <AppEntryGate />
      <UserOnboardingGate />
      <RouteFeatureLoader />
      <BalanceAnchorGuard />
      <CustomerParityHub />
      <WalletParity />
      <WalletEmailInputGuard />
      <PartnerRoxTransfer />
      <GenerationQuantityControl />
      <GenerationQuoteFreshnessGuard />
      <GenerationSubmitGuard />
      <UploadInputResetGuard />
      <PostPublishSharePrompt />
      <UnpublishFeedbackGuard />
      <GlobalUxEnhancers />
      <HistoryPromptCopyUx />
      <PrivateRepeatLinkUx />
      <KlingMultishotGuard />
      <InlineTrendAdmin />
    </ReferenceMemoryProvider>
  );
}
