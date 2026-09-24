"use client";

import React, { useEffect, useState, useCallback } from "react";
import { api, Order, API_BASE_URL } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";
import { getUser, UserSession } from "@/lib/auth";
import OrderTable from "@/components/OrderTable";

const STATUS_FILTERS = [
  "ALL",
  "NOT_STARTED",
  "AWAITING_PAYMENT",
  "PAYMENT_RECEIVED",
  "FULFILLED",
  "PAYMENT_RECONCILE",
];

export default function OrderDashboardPage() {
  const { t } = useI18n();
  const [orders, setOrders] = useState<Order[]>([]);
  const [selectedStatus, setSelectedStatus] = useState("ALL");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<UserSession | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportSuccess, setExportSuccess] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    setUser(getUser());
  }, []);

  const handleExport = async (carrierId: string = "kerry") => {
    setIsExporting(true);
    setExportError(null);
    setExportSuccess(null);
    try {
      const role = user?.role || "staff";
      const res = await fetch(`${API_BASE_URL}/api/export/csv?carrier_id=${carrierId}`, {
        headers: {
          "X-User-Role": role,
        },
      });
      if (!res.ok) {
        let msg = `Export failed with status ${res.status}`;
        try {
          const errData = await res.json();
          if (errData && errData.detail) msg = errData.detail;
        } catch {}
        setExportError(msg);
        return;
      }
      setExportSuccess(`Successfully exported ${carrierId} CSV`);
    } catch (err: any) {
      setExportError(err.message || "Export failed");
    } finally {
      setIsExporting(false);
    }
  };

  const fetchOrders = useCallback(async (status: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getOrders({
        status: status === "ALL" ? undefined : status,
      });
      setOrders(data);
    } catch {
      setError(t("orders_error"));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchOrders(selectedStatus);
  }, [fetchOrders, selectedStatus]);

  const getStatusFilterLabel = (status: string) => {
    if (status === "ALL") return t("filter_all");
    return t(`status_${status}`) || status;
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {t("orders_title")}
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {t("orders_subtitle")}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {error && (
            <button
              type="button"
              onClick={() => fetchOrders(selectedStatus)}
              className="inline-flex items-center px-3 py-1.5 border border-transparent rounded text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700"
            >
              {t("retry_button")}
            </button>
          )}

          <button
            type="button"
            data-testid="btn-export-csv"
            disabled={user?.role !== "owner" || isExporting}
            onClick={() => handleExport("kerry")}
            className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md text-xs font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            title={
              user?.role !== "owner"
                ? "Staff role cannot trigger carrier export. Owner permission required."
                : "Export Kerry CSV"
            }
          >
            {isExporting ? "Exporting..." : "Export Kerry CSV"}
          </button>
          <button
            type="button"
            data-testid="btn-export-thailand-post"
            disabled={user?.role !== "owner" || isExporting}
            onClick={() => handleExport("thailand_post")}
            className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md text-xs font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            title={
              user?.role !== "owner"
                ? "Staff role cannot trigger carrier export. Owner permission required."
                : "Export Thailand Post CSV"
            }
          >
            {isExporting ? "Exporting..." : "Export Thailand Post CSV"}
          </button>
        </div>
      </div>

      {exportError && (
        <div
          data-testid="export-error"
          className="p-3 rounded-md bg-red-50 dark:bg-red-900/50 text-red-700 dark:text-red-200 text-sm font-medium"
        >
          {exportError}
        </div>
      )}
      {exportSuccess && (
        <div
          data-testid="export-success"
          className="p-3 rounded-md bg-green-50 dark:bg-green-900/50 text-green-700 dark:text-green-200 text-sm font-medium"
        >
          {exportSuccess}
        </div>
      )}

      {/* Status filter tabs */}
      <div className="flex flex-wrap gap-2 pb-2">
        {STATUS_FILTERS.map((st) => {
          const isSelected = selectedStatus === st;
          return (
            <button
              key={st}
              type="button"
              onClick={() => setSelectedStatus(st)}
              data-testid={`filter-${st}`}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                isSelected
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700"
              }`}
            >
              {getStatusFilterLabel(st)}
            </button>
          );
        })}
      </div>

      {/* Orders Table */}
      <OrderTable orders={orders} isLoading={isLoading} error={error} />
    </div>
  );
}
