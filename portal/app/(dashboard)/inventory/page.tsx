"use client";

import React, { useEffect, useState, useCallback } from "react";
import { api, InventoryItem } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";
import InventoryTable from "@/components/InventoryTable";

export default function InventoryPage() {
  const { t } = useI18n();
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchInventory = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getInventory();
      setItems(data);
    } catch {
      setError(t("inv_error"));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchInventory();
  }, [fetchInventory]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {t("inventory_title")}
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {t("inventory_subtitle")}
          </p>
        </div>

        <button
          type="button"
          onClick={fetchInventory}
          className="inline-flex items-center px-3 py-1.5 border border-transparent rounded text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700"
        >
          {t("retry_button")}
        </button>
      </div>

      <InventoryTable items={items} isLoading={isLoading} error={error} />
    </div>
  );
}
