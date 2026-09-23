import thTranslations from "@/locale/th.json";
import enTranslations from "@/locale/en.json";

export type Locale = "th" | "en";
export type TranslationKey = keyof typeof thTranslations;

export const translations: Record<Locale, Record<string, string>> = {
  th: thTranslations,
  en: enTranslations,
};

export const DEFAULT_LOCALE: Locale = "th";
export const STORAGE_KEY_LOCALE = "user_prefs_language";

export function translate(
  locale: Locale,
  key: TranslationKey | string,
  params?: Record<string, string | number>
): string {
  const dict = translations[locale] || translations[DEFAULT_LOCALE];
  let text = dict[key] || translations[DEFAULT_LOCALE][key] || key;

  if (params) {
    Object.entries(params).forEach(([paramKey, paramVal]) => {
      text = text.replace(new RegExp(`\\{${paramKey}\\}`, "g"), String(paramVal));
    });
  }

  return text;
}
