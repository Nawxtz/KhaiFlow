"use client";

import React from "react";
import { useI18n } from "@/context/I18nContext";

interface OrderStatusBadgeProps {
  status: string;
}

export default function OrderStatusBadge({ status }: OrderStatusBadgeProps) {
  const { t } = useI18n();

  const getStatusColor = (st: string) => {
    switch (st) {
      case "NOT_STARTED":
      case "ORDER_DRAFT":
      case "BROWSING":
      case "EXPIRED":
        return "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600";
      case "AWAITING_PAYMENT":
      case "AWAITING_SELLER_APPROVAL":
      case "ORDER_CONFIRMED":
        return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700";
      case "PAYMENT_RECEIVED":
        return "bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300 border-blue-300 dark:border-blue-700";
      case "FULFILLED":
        return "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300 border-green-300 dark:border-green-700";
      case "PAYMENT_RECONCILE":
      case "CANCELLED":
        return "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300 border-red-300 dark:border-red-700";
      default:
        return "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600";
    }
  };

  const statusKey = `status_${status}`;
  const label = t(statusKey) || status;

  return (
    <span
      data-testid="order-status-badge"
      data-status={status}
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${getStatusColor(
        status
      )}`}
    >
      {label}
    </span>
  );
}
