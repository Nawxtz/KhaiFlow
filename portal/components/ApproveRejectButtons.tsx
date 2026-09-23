"use client";

import React, { useState } from "react";
import { api, ManualActionResponse } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";
import { getUser } from "@/lib/auth";

interface ApproveRejectButtonsProps {
  orderId: string;
  onSuccess?: (action: "approved" | "rejected", result: ManualActionResponse) => void;
  disabled?: boolean;
}

export default function ApproveRejectButtons({
  orderId,
  onSuccess,
  disabled = false,
}: ApproveRejectButtonsProps) {
  const { t } = useI18n();
  const [isRejectOpen, setIsRejectOpen] = useState(false);
  const [rejectionReason, setRejectionReason] = useState("");
  const [rejectError, setRejectError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [isError, setIsError] = useState(false);

  const getReviewerId = (): string => {
    const user = getUser();
    return user ? user.username : "seller_portal";
  };

  const handleApprove = async () => {
    setIsLoading(true);
    setActionMessage(null);
    setIsError(false);
    try {
      const reviewerId = getReviewerId();
      const res = await api.approveOrder(orderId, { reviewer_id: reviewerId });
      setActionMessage(t("action_success_approved"));
      setIsError(false);
      if (onSuccess) {
        onSuccess("approved", res);
      }
    } catch (err) {
      setIsError(true);
      setActionMessage(t("action_error_failed"));
    } finally {
      setIsLoading(false);
    }
  };

  const handleRejectSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejectionReason.trim()) {
      setRejectError(t("rejection_reason_required"));
      return;
    }

    setIsLoading(true);
    setActionMessage(null);
    setIsError(false);
    setRejectError("");

    try {
      const reviewerId = getReviewerId();
      const res = await api.rejectOrder(orderId, {
        reviewer_id: reviewerId,
        reason: rejectionReason.trim(),
      });
      setIsRejectOpen(false);
      setRejectionReason("");
      setActionMessage(t("action_success_rejected"));
      setIsError(false);
      if (onSuccess) {
        onSuccess("rejected", res);
      }
    } catch (err) {
      setIsError(true);
      setActionMessage(t("action_error_failed"));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {actionMessage && (
        <div
          data-testid="action-feedback"
          className={`p-3 rounded-md text-sm font-medium ${
            isError
              ? "bg-red-50 text-red-700 dark:bg-red-900/50 dark:text-red-200"
              : "bg-green-50 text-green-700 dark:bg-green-900/50 dark:text-green-200"
          }`}
        >
          {actionMessage}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleApprove}
          disabled={disabled || isLoading}
          data-testid="btn-approve"
          className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 disabled:opacity-50 transition-colors"
        >
          {isLoading ? t("action_processing") : t("action_approve")}
        </button>

        <button
          type="button"
          onClick={() => {
            setIsRejectOpen(true);
            setRejectError("");
          }}
          disabled={disabled || isLoading}
          data-testid="btn-reject"
          className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 transition-colors"
        >
          {t("action_reject")}
        </button>
      </div>

      {isRejectOpen && (
        <div
          data-testid="reject-dialog"
          className="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600 space-y-3"
        >
          <h4 className="text-sm font-semibold text-gray-900 dark:text-white">
            {t("confirm_reject_title")}
          </h4>
          <p className="text-xs text-gray-600 dark:text-gray-300">
            {t("confirm_reject_desc", { order_id: orderId })}
          </p>

          <form onSubmit={handleRejectSubmit} className="space-y-3">
            <div>
              <label
                htmlFor="reject-reason"
                className="block text-xs font-medium text-gray-700 dark:text-gray-200"
              >
                {t("rejection_reason_label")}
              </label>
              <input
                id="reject-reason"
                type="text"
                value={rejectionReason}
                onChange={(e) => {
                  setRejectionReason(e.target.value);
                  if (rejectError) setRejectError("");
                }}
                placeholder={t("rejection_reason_placeholder")}
                data-testid="input-reject-reason"
                className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm shadow-sm focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500"
              />
              {rejectError && (
                <p
                  data-testid="reject-error"
                  className="mt-1 text-xs text-red-600 dark:text-red-400 font-medium"
                >
                  {rejectError}
                </p>
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                type="submit"
                disabled={isLoading}
                data-testid="btn-confirm-reject"
                className="inline-flex items-center px-3 py-1.5 border border-transparent rounded text-xs font-medium text-white bg-red-600 hover:bg-red-700 focus:outline-none disabled:opacity-50 transition-colors"
              >
                {isLoading ? t("action_processing") : t("btn_confirm")}
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsRejectOpen(false);
                  setRejectionReason("");
                  setRejectError("");
                }}
                disabled={isLoading}
                data-testid="btn-cancel-reject"
                className="inline-flex items-center px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded text-xs font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none transition-colors"
              >
                {t("btn_cancel")}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
