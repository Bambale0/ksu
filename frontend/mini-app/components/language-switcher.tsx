"use client";

import { useState } from "react";

import { useUiLanguage } from "@/components/ui-language-provider";
import type { UiLanguage } from "@/lib/ui-language";

export function LanguageSwitcher() {
  const { language, saving, syncError, selectLanguage, t } = useUiLanguage();
  const [localError, setLocalError] = useState("");

  const choose = async (next: UiLanguage) => {
    if (next === language || saving) return;
    setLocalError("");
    try {
      await selectLanguage(next);
    } catch {
      setLocalError(t("Не удалось сохранить настройки"));
    }
  };

  const error = localError || syncError;

  return (
    <div className="language-switcher-wrap">
      <div className="language-switcher" role="group" aria-label={t("Язык интерфейса")}>
        {(["ru", "en"] as const).map((item) => (
          <button
            key={item}
            type="button"
            aria-pressed={language === item}
            disabled={saving}
            onClick={() => void choose(item)}
          >
            {item.toUpperCase()}
          </button>
        ))}
      </div>
      {error ? <span className="language-sync-error" role="status" title={error}>!</span> : null}
    </div>
  );
}
