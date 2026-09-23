"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import {
  DEFAULT_LOCALE,
  Locale,
  STORAGE_KEY_LOCALE,
  TranslationKey,
  translate,
} from "@/lib/i18n";

interface I18nContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey | string, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextType | undefined>(undefined);

export function I18nProvider({
  children,
  initialLocale = DEFAULT_LOCALE,
}: {
  children: React.ReactNode;
  initialLocale?: Locale;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY_LOCALE) as Locale | null;
      if (stored === "th" || stored === "en") {
        setLocaleState(stored);
      }
    } catch {
      // localStorage may fail in SSR or restricted environments
    }
  }, []);

  const setLocale = (newLocale: Locale) => {
    setLocaleState(newLocale);
    try {
      localStorage.setItem(STORAGE_KEY_LOCALE, newLocale);
    } catch {
      // ignore storage errors
    }
  };

  const t = (key: TranslationKey | string, params?: Record<string, string | number>) => {
    return translate(locale, key, params);
  };

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return context;
}
