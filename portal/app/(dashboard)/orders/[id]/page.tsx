"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, Order } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";
import OrderStatusBadge from "@/components/OrderStatusBadge";
import ApproveRejectButtons from "@/components/ApproveRejectButtons";

export default function OrderDetailPage() {
  const { t } = useI18n();
  const params = useParams();
  const orderId = params?.id as string;

  const [order, setOrder] = useState<Order | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchOrder = useCallback(async (isInitial = false) => {
    if (!orderId) return;
    if (isInitial) setIsLoading(true);
    setError(null);
    try {
      const data = await api.getOrder(orderId);
      setOrder(data);
    } catch {
      if (isInitial) setError(t("orders_error"));
    } finally {
      if (isInitial) setIsLoading(false);
    }
  }, [orderId, t]);

  useEffect(() => {
    fetchOrder(true);
  }, [fetchOrder]);

  if (isLoading) {
    return (
      <div
        data-testid="order-detail-loading"
        className="p-12 text-center text-gray-500 dark:text-gray-400"
      >
        {t("orders_loading")}
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="p-8 text-center bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700">
        <p
          data-testid="order-detail-error"
          className="text-red-600 dark:text-red-400 font-medium mb-4"
        >
          {error || t("orders_empty")}
        </p>
        <Link
          href="/"
          className="inline-flex items-center px-4 py-2 border border-transparent rounded-md text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700"
        >
          {t("back_to_orders")}
        </Link>
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
    <div className="space-y-6">
      {/* Back link & Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <Link
            href="/"
            data-testid="link-back-orders"
            className="inline-flex items-center text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:underline mb-2"
          >
            ← {t("back_to_orders")}
          </Link>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {t("order_detail_title")}: {order.id}
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {t("order_detail_subtitle")}
          </p>
        </div>
        <div className="flex items-center">
          <OrderStatusBadge status={order.status} />
        </div>
      </div>

      {/* Order info summary */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          {t("order_info_heading")}
        </h2>
        <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <dt className="text-xs font-medium text-gray-500 dark:text-gray-400">
              {t("order_id_label")}
            </dt>
            <dd className="mt-1 text-sm font-semibold text-gray-900 dark:text-white">
              {order.id}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-gray-500 dark:text-gray-400">
              {t("buyer_id_label")}
            </dt>
            <dd className="mt-1 text-sm text-gray-900 dark:text-white">
              {order.line_user_id}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-gray-500 dark:text-gray-400">
              {t("order_created_label")}
            </dt>
            <dd className="mt-1 text-sm text-gray-900 dark:text-white">
              {formatDate(order.created_at)}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-gray-500 dark:text-gray-400">
              {t("order_total_label")}
            </dt>
            <dd className="mt-1 text-base font-bold text-indigo-600 dark:text-indigo-400">
              {formatAmount(order.total, order.currency)}
            </dd>
          </div>
        </dl>
      </div>

      {/* Payment verification (Option B) section */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 p-6 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            {t("verification_heading")}
          </h2>
          {order.approval_state === "AWAITING_SELLER_APPROVAL" && (
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300">
              {t("manual_review_notice")}
            </span>
          )}
        </div>

        <dl className="grid grid-cols-1 sm:grid-cols-3 gap-4 border-t border-b border-gray-200 dark:border-gray-700 py-4">
          <div>
            <dt className="text-xs font-medium text-gray-500 dark:text-gray-400">
              {t("risk_score_label")}
            </dt>
            <dd
              data-testid="order-risk-score"
              className={`mt-1 text-sm font-semibold ${
                order.risk_score && order.risk_score >= 80
                  ? "text-red-600 dark:text-red-400"
                  : "text-gray-900 dark:text-white"
              }`}
            >
              {order.risk_score !== null && order.risk_score !== undefined
                ? order.risk_score
                : t("na")}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-gray-500 dark:text-gray-400">
              {t("payment_ref_label")}
            </dt>
            <dd
              data-testid="order-payment-ref"
              className="mt-1 text-sm font-mono text-gray-900 dark:text-white"
            >
              {order.payment_ref || t("na")}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-gray-500 dark:text-gray-400">
              {t("approval_state_label")}
            </dt>
            <dd
              data-testid="order-approval-state"
              className="mt-1 text-sm font-semibold text-gray-900 dark:text-white"
            >
              {order.approval_state || t("na")}
            </dd>
          </div>
        </dl>

        {/* Option B action buttons */}
        <div className="pt-2">
          <ApproveRejectButtons
            orderId={order.id}
            onSuccess={() => {
              fetchOrder(false);
            }}
          />
        </div>
      </div>

      {/* Items list */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          {t("items_heading")}
        </h2>

        {!order.items || order.items.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">{t("no_items")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th
                    scope="col"
                    className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase"
                  >
                    {t("item_sku")}
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase"
                  >
                    {t("item_name")}
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase"
                  >
                    {t("item_size")}
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase"
                  >
                    {t("item_qty")}
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-300 uppercase"
                  >
                    {t("item_unit_price")}
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-300 uppercase"
                  >
                    {t("item_line_total")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {order.items.map((item) => (
                  <tr key={item.id}>
                    <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                      {item.sku}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300">
                      {item.name}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {item.size || t("na")}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300">
                      {item.qty}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-right text-gray-700 dark:text-gray-300">
                      {formatAmount(item.unit_price, order.currency)}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-right font-semibold text-gray-900 dark:text-white">
                      {formatAmount(item.line_total, order.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
