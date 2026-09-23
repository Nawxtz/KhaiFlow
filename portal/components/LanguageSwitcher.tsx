"use client";

import React from "react";
import { useI18n } from "@/context/I18nContext";

export default function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n();

  const toggleLanguage = () => {
    const nextLocale = locale === "th" ? "en" : "th";
    setLocale(nextLocale);
  };

  return (
    <button
      type="button"
      onClick={toggleLanguage}
      title={t("switch_language")}
      aria-label={t("switch_language")}
      className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors"
      data-testid="language-switcher"
    >
      <span className="font-semibold">{locale === "th" ? t("lang_en") : t("lang_th")}</span>
    </button>
  );
}
