/**
 * A non-secret hint cookie set by the frontend after a login or refresh: "this browser
 * probably has a refresh cookie". The refresh cookie itself is HttpOnly, so without the
 * hint every guest page load would cost a refresh call. The hint grants nothing; the
 * server still decides.
 */

const NAME = "ak_session";
const MAX_AGE_SECONDS = 30 * 24 * 60 * 60;

export function hasSessionHint(): boolean {
  if (typeof document === "undefined") return false;
  return document.cookie.split(";").some((part) => part.trim() === `${NAME}=1`);
}

export function setSessionHint(): void {
  if (typeof document === "undefined") return;
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${NAME}=1; Path=/; Max-Age=${MAX_AGE_SECONDS}; SameSite=Lax${secure}`;
}

export function clearSessionHint(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${NAME}=; Path=/; Max-Age=0; SameSite=Lax`;
}
