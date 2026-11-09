export const CSRF_COOKIE = "kf_csrf";
export const CSRF_HEADER = "X-CSRF-Token";

export function csrfHeaders(): Record<string, string> {
  if (typeof document === "undefined") return {};
  const entry = document.cookie
    .split("; ")
    .find((part) => part.startsWith(`${CSRF_COOKIE}=`));
  return entry ? { [CSRF_HEADER]: decodeURIComponent(entry.split("=")[1]) } : {};
}
