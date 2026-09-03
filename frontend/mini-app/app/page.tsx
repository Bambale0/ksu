import { AiReferenceHomeEntry } from "@/components/ai-reference-home-entry";
import { AppEntryGate } from "@/components/app-entry-gate";
import { BalanceAnchorGuard } from "@/components/balance-anchor-guard";
import { CatalogFeatureHub } from "@/components/catalog-feature-hub";
import { CatalogParityFeatures } from "@/components/catalog-parity-features";
import { CatalogTrendFolders } from "@/components/catalog-trend-folders";
import { ClientErrorReporter } from "@/components/client-error-reporter";
import { CustomerParityHub } from "@/components/customer-parity-hub";
import { FeedAdminModeration } from "@/components/feed-admin-moderation";
import { FeedResponsiveLayout } from "@/components/feed-responsive-layout";
import { GenerationQuantityControl } from "@/components/generation-quantity-control";
import { GlobalUxEnhancers } from "@/components/global-ux-enhancers";
import { HistoryPromptCopyUx } from "@/components/history-prompt-copy-ux";
import { HomeTrendFolders } from "@/components/home-trend-folders";
import { InlineTrendAdmin } from "@/components/inline-trend-admin";
import { KlingMultishotGuard } from "@/components/kling-multishot-guard";
import { LiveTrendRail } from "@/components/live-trend-rail";
import { PartnerRoxTransfer } from "@/components/partner-rox-transfer";
import { PostPublishSharePrompt } from "@/components/post-publish-share-prompt";
import { PrivateRepeatLinkUx } from "@/components/private-repeat-link-ux";
import { TikTokFeedSurface } from "@/components/tiktok-feed-surface";
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
      <TikTokFeedSurface />
      <FeedResponsiveLayout />
      <FeedAdminModeration />
      <BalanceAnchorGuard />
      <CatalogFeatureHub />
      <LiveTrendRail />
      <HomeTrendFolders />
      <AiReferenceHomeEntry />
      <CatalogTrendFolders />
      <CatalogParityFeatures />
      <CustomerParityHub />
      <WalletParity />
      <WalletEmailInputGuard />
      <PartnerRoxTransfer />
      <GenerationQuantityControl />
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
