"use client";

import React from "react";
import { InventoryItem } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";

interface InventoryTableProps {
  items: InventoryItem[];
  isLoading?: boolean;
  error?: string | null;
}

export default function InventoryTable({ items, isLoading, error }: InventoryTableProps) {
  const { t } = useI18n();

  if (isLoading) {
    return (
      <div
        data-testid="inventory-loading"
        className="p-8 text-center text-gray-500 dark:text-gray-400"
      >
        {t("inv_loading")}
      </div>
    );
  }

  if (error) {
    return (
      <div
        data-testid="inventory-error"
        className="p-8 text-center text-red-600 dark:text-red-400"
      >
        {error || t("inv_error")}
      </div>
    );
  }

  if (!items || items.length === 0) {
    return (
      <div
        data-testid="inventory-empty"
        className="p-8 text-center text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700"
      >
        {t("inv_empty")}
      </div>
    );
  }

  const formatPrice = (val: number) => {
    return `${val.toFixed(2)} ${t("currency_thb")}`;
  };

  return (
    <div className="overflow-x-auto bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700">
      <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead className="bg-gray-50 dark:bg-gray-700">
          <tr>
            <th
              scope="col"
              className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              {t("inv_col_sku")}
            </th>
            <th
              scope="col"
              className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              {t("inv_col_name")}
            </th>
            <th
              scope="col"
              className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              {t("inv_col_category")}
            </th>
            <th
              scope="col"
              className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              {t("inv_col_price")}
            </th>
            <th
              scope="col"
              className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              {t("inv_col_stock")}
            </th>
            <th
              scope="col"
              className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              {t("inv_col_reserved")}
            </th>
            <th
              scope="col"
              className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              {t("inv_col_available")}
            </th>
            <th
              scope="col"
              className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              {t("inv_col_status")}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
          {items.map((item) => {
            const available =
              item.available_stock !== undefined
                ? item.available_stock
                : Math.max(0, item.stock - item.reserved);

            return (
              <tr
                key={item.sku}
                className="hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors"
                data-testid={`inventory-row-${item.sku}`}
              >
                <td className="px-6 py-4 whitespace-nowrap text-sm font-semibold text-gray-900 dark:text-white">
                  {item.sku}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-800 dark:text-gray-200">
                  {item.name}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                  {item.category}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white font-medium">
                  {formatPrice(item.price)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300">
                  {item.stock}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-yellow-600 dark:text-yellow-400 font-medium">
                  {item.reserved}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-bold text-green-600 dark:text-green-400">
                  {available}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                      item.active
                        ? "bg-green-100 text-green-800 dark:bg-green-900/60 dark:text-green-300"
                        : "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300"
                    }`}
                  >
                    {item.active ? t("inv_status_active") : t("inv_status_inactive")}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
