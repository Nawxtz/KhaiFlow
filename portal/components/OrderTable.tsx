"use client";

import React from "react";
import Link from "next/link";
import { Order } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";
import OrderStatusBadge from "@/components/OrderStatusBadge";

interface OrderTableProps {
  orders: Order[];
  isLoading?: boolean;
  error?: string | null;
}

export default function OrderTable({ orders, isLoading, error }: OrderTableProps) {
  const { t } = useI18n();

  if (isLoading) {
    return (
      <div
        data-testid="order-table-loading"
        className="p-8 text-center text-gray-500 dark:text-gray-400"
      >
        {t("orders_loading")}
      </div>
    );
  }

  if (error) {
    return (
      <div
        data-testid="order-table-error"
        className="p-8 text-center text-red-600 dark:text-red-400"
      >
        {error || t("orders_error")}
      </div>
    );
  }

  if (!orders || orders.length === 0) {
    return (
      <div
        data-testid="order-table-empty"
        className="p-8 text-center text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700"
      >
        {t("orders_empty")}
      </div>
    );
  }

  const formatAmount = (val: number | string, curr: string) => {
    const num = typeof val === "string" ? parseFloat(val) : val;
    const formatted = isNaN(num) ? "0.00" : num.toFixed(2);
    return `${formatted} ${curr || t("currency_thb")}`;
  };

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleString();
    } catch {
      return dateStr;
    }
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
              {t("order_col_id")}
            </th>
            <th
              scope="col"
              className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              {t("order_col_buyer")}
            </th>
            <th
              scope="col"
              className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              {t("order_col_items_count")}
            </th>
            <th
              scope="col"
              className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              {t("order_col_total")}
            </th>
            <th
              scope="col"
              className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              {t("order_col_status")}
            </th>
            <th
              scope="col"
              className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              {t("order_col_created")}
            </th>
            <th
              scope="col"
              className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider"
            >
              {t("order_col_actions")}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
          {orders.map((order) => {
            const itemsCount = order.items ? order.items.length : 0;
            return (
              <tr
                key={order.id}
                className="hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors"
                data-testid={`order-row-${order.id}`}
              >
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-indigo-600 dark:text-indigo-400">
                  <Link href={`/orders/${order.id}`} className="hover:underline">
                    {order.id}
                  </Link>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300">
                  {order.line_user_id}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300">
                  {itemsCount}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-semibold text-gray-900 dark:text-white">
                  {formatAmount(order.total, order.currency)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  <OrderStatusBadge status={order.status} />
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                  {formatDate(order.created_at)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <Link
                    href={`/orders/${order.id}`}
                    className="inline-flex items-center px-3 py-1.5 border border-transparent text-xs font-medium rounded text-indigo-700 bg-indigo-100 hover:bg-indigo-200 dark:text-indigo-300 dark:bg-indigo-900/60 dark:hover:bg-indigo-900 focus:outline-none transition-colors"
                  >
                    {t("view_details")}
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
