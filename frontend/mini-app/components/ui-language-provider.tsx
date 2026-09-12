"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { customerRequest } from "@/lib/customer-api";
import { telegram } from "@/lib/telegram";
import {
  resolveUiLanguage,
  translateUiText,
  type UiLanguage,
} from "@/lib/ui-language";

type Preferences = {
  ui_language: string;
  notifications_enabled: boolean;
  marketing_notifications: boolean;
  profile_discoverable: boolean;
};

type UiLanguageContextValue = {
  language: UiLanguage;
  saving: boolean;
  syncError: string;
  selectLanguage: (language: UiLanguage) => Promise<void>;
  t: (value: string) => string;
};

const LANGUAGE_STORAGE_KEY = "roxy-ui-language";
const TRANSLATED_ATTRIBUTES = ["placeholder", "aria-label", "title", "alt"] as const;
const SKIP_TRANSLATION_SELECTOR = [
  "script",
  "style",
  "pre",
  "code",
  "textarea",
  "[contenteditable='true']",
  "[data-no-i18n]",
  ".prompt-copy",
].join(",");

const UiLanguageContext = createContext<UiLanguageContextValue | null>(null);

function savedLanguage(): UiLanguage | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return value === "ru" || value === "en" ? value : null;
  } catch {
    return null;
  }
}

function telegramLanguageCode(): string {
  return String(telegram()?.initDataUnsafe?.user?.language_code || "");
}

function persistLocalLanguage(language: UiLanguage): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Some restrictive WebViews disable localStorage. Account persistence still works.
  }
}

function shouldSkip(node: Node): boolean {
  const element = node instanceof Element ? node : node.parentElement;
  return Boolean(element?.closest(SKIP_TRANSLATION_SELECTOR));
}

function translateTextNode(node: Text, language: UiLanguage): void {
  if (shouldSkip(node)) return;
  const current = node.nodeValue || "";
  const next = translateUiText(current, language);
  if (next !== current) node.nodeValue = next;
}

function translateElementAttributes(element: Element, language: UiLanguage): void {
  if (shouldSkip(element)) return;
  for (const name of TRANSLATED_ATTRIBUTES) {
    const current = element.getAttribute(name);
    if (!current) continue;
    const next = translateUiText(current, language);
    if (next !== current) element.setAttribute(name, next);
  }
}

function translateSubtree(root: Node, language: UiLanguage): void {
  if (root instanceof Text) {
    translateTextNode(root, language);
    return;
  }
  if (root instanceof Element) translateElementAttributes(root, language);
  if (!(root instanceof Element || root instanceof Document || root instanceof DocumentFragment)) return;
  if (root instanceof Element && shouldSkip(root)) return;

  const owner = root instanceof Document ? root : root.ownerDocument;
  if (!owner) return;
  const walker = owner.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
  let current = walker.nextNode();
  while (current) {
    if (current instanceof Text) translateTextNode(current, language);
    else if (current instanceof Element) translateElementAttributes(current, language);
    current = walker.nextNode();
  }
}

function useDomTranslation(language: UiLanguage): void {
  useEffect(() => {
    document.documentElement.lang = language;
    translateSubtree(document.body, language);

    let scheduled = false;
    const pending = new Set<Node>();
    const flush = () => {
      scheduled = false;
      for (const node of pending) translateSubtree(node, language);
      pending.clear();
    };
    const schedule = (node: Node) => {
      pending.add(node);
      if (scheduled) return;
      scheduled = true;
      window.requestAnimationFrame(flush);
    };

    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "characterData") {
          schedule(record.target);
          continue;
        }
        if (record.type === "attributes") {
          schedule(record.target);
          continue;
        }
        for (const node of record.addedNodes) schedule(node);
      }
    });
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: [...TRANSLATED_ATTRIBUTES],
    });
    return () => observer.disconnect();
  }, [language]);
}

export function UiLanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<UiLanguage>("ru");
  const [saving, setSaving] = useState(false);
  const [syncError, setSyncError] = useState("");
  const preferencesRef = useRef<Preferences | null>(null);
  const manualSelectionRef = useRef(false);

  useDomTranslation(language);

  useEffect(() => {
    const local = savedLanguage();
    if (local) setLanguage(local);
    else setLanguage(resolveUiLanguage("auto", telegramLanguageCode()));

    let active = true;
    void customerRequest<Preferences>("/api/v1/me/preferences")
      .then((preferences) => {
        if (!active) return;
        preferencesRef.current = preferences;
        if (manualSelectionRef.current) return;
        const resolved = resolveUiLanguage(preferences.ui_language, telegramLanguageCode());
        setLanguage(resolved);
        persistLocalLanguage(resolved);
      })
      .catch(() => {
        // Language remains usable locally even when preference sync is temporarily unavailable.
      });

    return () => {
      active = false;
    };
  }, []);

  const selectLanguage = useCallback(async (next: UiLanguage) => {
    manualSelectionRef.current = true;
    setLanguage(next);
    persistLocalLanguage(next);
    setSyncError("");
    setSaving(true);

    try {
      // Re-read before PUT so a language change never overwrites notification
      // or discoverability changes saved from another Mini App surface.
      const current = await customerRequest<Preferences>("/api/v1/me/preferences");
      const updated = await customerRequest<Preferences>("/api/v1/me/preferences", {
        method: "PUT",
        body: JSON.stringify({ ...current, ui_language: next }),
      });
      preferencesRef.current = updated;
    } catch (error) {
      setSyncError(error instanceof Error ? error.message : "Language preference could not be synced");
      throw error;
    } finally {
      setSaving(false);
    }
  }, []);

  const value = useMemo<UiLanguageContextValue>(() => ({
    language,
    saving,
    syncError,
    selectLanguage,
    t: (text) => translateUiText(text, language),
  }), [language, saving, selectLanguage, syncError]);

  return <UiLanguageContext.Provider value={value}>{children}</UiLanguageContext.Provider>;
}

export function useUiLanguage(): UiLanguageContextValue {
  const value = useContext(UiLanguageContext);
  if (!value) throw new Error("useUiLanguage must be used inside UiLanguageProvider");
  return value;
}
