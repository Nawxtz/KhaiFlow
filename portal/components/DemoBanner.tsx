"use client";

import { useI18n } from "@/context/I18nContext";

export default function DemoBanner() {
  const { t } = useI18n();

  return (
    <div
      role="status"
      data-testid="demo-banner"
      className="bg-amber-100 dark:bg-amber-900 text-amber-900 dark:text-amber-100 text-center text-sm px-4 py-2"
    >
      {t("demo_banner")}
    </div>
  );
}
