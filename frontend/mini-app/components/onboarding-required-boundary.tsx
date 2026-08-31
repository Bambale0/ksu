"use client";

import { type ReactNode, useLayoutEffect } from "react";

import {
  isOnboardingRequiredResponse,
  ONBOARDING_REQUIRED_MESSAGE,
  redirectToOnboarding,
} from "@/lib/onboarding-required";

function friendlyOnboardingResponse(response: Response): Response {
  const headers = new Headers(response.headers);
  headers.set("content-type", "application/json; charset=utf-8");
  return new Response(JSON.stringify({ detail: ONBOARDING_REQUIRED_MESSAGE }), {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export function OnboardingRequiredBoundary({ children }: { children: ReactNode }) {
  useLayoutEffect(() => {
    const nativeFetch = window.fetch.bind(window);

    const interceptedFetch: typeof window.fetch = async (...args) => {
      const response = await nativeFetch(...args);
      if (response.status !== 428) return response;

      const payload = await response.clone().json().catch(() => null);
      if (!isOnboardingRequiredResponse(response.status, payload)) return response;

      // The backend gate is intentional: never weaken it. Convert its technical
      // protocol response into the existing first-run ROXY experience instead.
      redirectToOnboarding();
      return friendlyOnboardingResponse(response);
    };

    window.fetch = interceptedFetch;
    return () => {
      if (window.fetch === interceptedFetch) window.fetch = nativeFetch;
    };
  }, []);

  return children;
}
