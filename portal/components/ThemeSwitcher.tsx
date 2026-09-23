"use client";

import React from "react";
import { useTheme } from "@/context/ThemeContext";
import { useI18n } from "@/context/I18nContext";

export default function ThemeSwitcher() {
  const { theme, toggleTheme } = useTheme();
  const { t } = useI18n();

  const label = theme === "dark" ? t("switch_to_light") : t("switch_to_dark");

  return (
    <button
      type="button"
      onClick={toggleTheme}
      title={label}
      aria-label={label}
      className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors"
      data-testid="theme-switcher"
    >
      <span>{theme === "dark" ? t("theme_light") : t("theme_dark")}</span>
    </button>
  );
}
