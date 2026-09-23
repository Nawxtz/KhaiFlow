"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useI18n } from "@/context/I18nContext";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import ThemeSwitcher from "@/components/ThemeSwitcher";
import { clearSession, getUser, UserSession } from "@/lib/auth";

export default function Navbar() {
  const { t } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<UserSession | null>(null);

  useEffect(() => {
    setUser(getUser());
  }, []);

  const handleLogout = () => {
    clearSession();
    router.push("/login");
  };

  const navLinks = [
    { href: "/", label: t("nav_orders") },
    { href: "/inventory", label: t("nav_inventory") },
  ];

  const getRoleLabel = (role: string) => {
    if (role === "owner") return t("user_role_owner");
    if (role === "staff") return t("user_role_staff");
    return role;
  };

  return (
    <nav className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 shadow-sm transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          {/* Left Brand and Links */}
          <div className="flex">
            <div className="flex-shrink-0 flex items-center">
              <Link
                href="/"
                className="text-lg font-bold text-indigo-600 dark:text-indigo-400 hover:opacity-90"
              >
                {t("app_title")}
              </Link>
            </div>
            <div className="hidden sm:ml-8 sm:flex sm:space-x-4 items-center">
              {navLinks.map((link) => {
                const isActive =
                  link.href === "/"
                    ? pathname === "/" || pathname?.startsWith("/orders")
                    : pathname === link.href;

                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    data-testid={link.href === "/" ? "nav-link-orders" : "nav-link-inventory"}
                    className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-indigo-50 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 font-semibold"
                        : "text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                    }`}
                  >
                    {link.label}
                  </Link>
                );
              })}
            </div>
          </div>

          {/* Right Controls */}
          <div className="flex items-center space-x-3">
            {user && (
              <span
                data-testid="navbar-user"
                className="hidden md:inline-block text-xs text-gray-500 dark:text-gray-400 font-medium"
              >
                {t("logged_in_as", {
                  name: user.username,
                  role: getRoleLabel(user.role),
                })}
              </span>
            )}

            <LanguageSwitcher />
            <ThemeSwitcher />

            <button
              type="button"
              onClick={handleLogout}
              data-testid="btn-logout"
              className="inline-flex items-center px-3 py-1.5 border border-transparent rounded-md text-sm font-medium text-white bg-gray-600 hover:bg-gray-700 dark:bg-gray-700 dark:hover:bg-gray-600 focus:outline-none transition-colors"
            >
              {t("nav_logout")}
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
