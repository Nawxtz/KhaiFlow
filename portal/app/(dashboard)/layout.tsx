"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";
import Navbar from "@/components/Navbar";
import { useI18n } from "@/context/I18nContext";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { t } = useI18n();
  const [isChecking, setIsChecking] = useState(true);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
    } else {
      setAuthed(true);
    }
    setIsChecking(false);
  }, [router]);

  if (isChecking || !authed) {
    return (
      <div
        data-testid="auth-loading"
        className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900"
      >
        <div className="text-gray-500 dark:text-gray-400 text-sm">
          {t("orders_loading")}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 transition-colors">
      <Navbar />
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8 px-4">
        {children}
      </main>
    </div>
  );
}
