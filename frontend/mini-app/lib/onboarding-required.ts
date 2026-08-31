export const ONBOARDING_REQUIRED_CODE = "onboarding_required";
export const ONBOARDING_REQUIRED_MESSAGE = "Сначала откроем ROXY — это займёт пару секунд";

function detailOf(payload: unknown): unknown {
  if (!payload || typeof payload !== "object") return null;
  return (payload as { detail?: unknown }).detail;
}

export function isOnboardingRequiredResponse(status: number, payload: unknown): boolean {
  if (status !== 428) return false;
  const detail = detailOf(payload);
  return Boolean(
    detail
      && typeof detail === "object"
      && (detail as { code?: unknown }).code === ONBOARDING_REQUIRED_CODE,
  );
}

export function redirectToOnboarding(): void {
  if (typeof window === "undefined") return;
  const target = "/mini-app/?onboarding=1";
  if (`${window.location.pathname}${window.location.search}` === target) return;
  window.location.replace(target);
}

export function handleOnboardingRequired(status: number, payload: unknown): boolean {
  if (!isOnboardingRequiredResponse(status, payload)) return false;
  redirectToOnboarding();
  return true;
}
