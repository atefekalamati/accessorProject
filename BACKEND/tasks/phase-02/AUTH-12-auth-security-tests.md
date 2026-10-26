# AUTH-12 — Auth API & security test suite

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 3h (estimate) · **Deadline:** — · **Dependencies:** AUTH-05 … AUTH-11 · **Level:** HIGH

## Objective
پوشش کامل معیارهای پذیرش «هویت و دسترسی» و سناریوهای سوءاستفاده.

## PRD reference
«هویت و دسترسی» ✓ (معیار پذیرش و تست)

## Acceptance Criteria
- [x] OTP منقضی یا مصرف‌شده دوباره قابل استفاده نیست.
- [x] درخواست زیاد OTP → 429.
- [x] verify موفق، access و refresh معتبر صادر می‌کند.
- [x] logout، refresh token را باطل می‌کند.
- [x] کاربر بدون نقش مدیریتی به endpointهای `/admin` دسترسی ندارد (403).
- [x] Admin نمی‌تواند نقش خود یا دیگران را به Super Admin تغییر دهد.
- [x] Customer فقط اطلاعات خودش را می‌بیند.
- [x] تغییرات نقش و وضعیت در Audit Log ثبت شده‌اند.
- [x] OTP و refresh token در دیتابیس به‌صورت plaintext وجود ندارند (بررسی مستقیم جدول).
- [x] مسیرهای 400، 401، 403، 404، 409، 422 و 429 پوشش داده شده‌اند.
- [x] cookie refresh ویژگی‌های `HttpOnly`، `Secure`، `SameSite=Strict` و Path درست را دارد و refresh token در body هیچ پاسخی نمی‌آید.

## Implementation Notes
`tests/test_auth_security.py` برای بررسی‌های cross-cutting. بقیه ruleها در suite همان endpoint تست شده‌اند (جدول زیر).

## Validation
```powershell
python -m pytest   # با TEST_DATABASE_URL
python -m ruff check .
python -m ruff format --check .
python -m mypy app tests
```

## Log
### 2026-10-09 — COMPLETE (batch AUTH-11/12)
- فایل جدید `tests/test_auth_security.py` (۷ مورد). docstring هر تست شناسه rule را دارد. تست‌های موجود تکرار نشدند.
  - `test_tokens_travel_only_where_allowed`
  - `test_no_plaintext_otp_or_refresh_token_in_the_database`: همه ستون‌ها به text cast و بررسی می‌شوند.
  - `test_every_admin_route_requires_authentication` و `test_customer_is_forbidden_on_every_admin_route`: routeهای `/admin` از OpenAPI کشف می‌شوند، پس endpointهای آینده خودکار پوشش داده می‌شوند. `test_admin_routes_are_discovered` مراقب است این کشف خالی نماند.
  - `test_customer_sees_and_edits_only_their_own_account`
- اصلاح کوچک در AUTH-11: در `GET /admin/users` چک permission به قبل از allowlist query منتقل شد، تا کاربر احرازنشده به‌جای 400 همان 401 را بگیرد.
- Validation: pytest 623 passed (با دیتابیس تست)، ruff، format و mypy سبز.

## نگاشت rule → تست
| Rule | تست |
|---|---|
| ADR-016 cooldown، سقف per-mobile/IP/سراسری → 429 + `Retry-After` | `test_auth_request_otp.py`: `..._resend_cooldown_returns_429`، `..._per_mobile_limit_returns_429`، `..._per_ip_limit_returns_429`، `..._global_cap_returns_429_and_logs_warning`، `..._ignores_codes_outside_window` |
| ADR-016 ابطال کد قبلی، پاسخ یکسان برای کاربر موجود و ناموجود | `test_request_otp_invalidates_previous_code`، `test_request_otp_response_does_not_reveal_user_existence` |
| ADR-016/017 hash به‌جای plaintext (OTP، refresh) | `test_auth_security.py::test_no_plaintext_otp_or_refresh_token_in_the_database`، `test_otp.py`، `test_auth_tokens.py::test_refresh_tokens_are_random_and_hashed` |
| ADR-017 OTP یک‌بارمصرف، منقضی، ۵ تلاش، خطای یکسان `OTP_INVALID` | `test_auth_verify_otp.py`: `test_code_is_single_use`، `test_concurrent_verifications_consume_the_code_once`، `test_expired_code_is_rejected`، `test_wrong_code_counts_attempts_and_fifth_failure_invalidates`، `test_unknown_mobile_gets_the_same_error` |
| ADR-017 verify، access و refresh معتبر صادر می‌کند | `test_first_login_creates_customer_and_issues_tokens` |
| ADR-017 حساب inactive/blocked/حذف‌شده | `test_disabled_account_gets_no_tokens`، `test_deleted_blocked_account_mobile_is_rejected`، `test_disabled_or_deleted_user_cannot_refresh` |
| ADR-017 JWT: HS256 ثابت، رد `none`، claimهای الزامی | `test_auth_tokens.py` (۹ مورد) |
| ADR-017/012 cookie `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth`، refresh در هیچ body نیست، `no-store` | `test_auth_security.py::test_tokens_travel_only_where_allowed`، `test_auth_me.py::test_auth_and_profile_responses_are_not_cacheable` |
| ADR-017 چرخش و reuse → revoke کل family | `test_auth_refresh.py`: `..._rotates_the_token_within_its_family`، `test_reuse_of_a_rotated_token_revokes_the_family`، `test_concurrent_refreshes_with_one_token_revoke_the_family`، `test_refresh_token_outside_the_cookie_is_ignored` |
| ADR-017/018 logout refresh را باطل می‌کند | `test_auth_logout.py::test_refresh_after_logout_is_unauthorized`، `test_logout_revokes_the_session_and_clears_the_cookie` |
| ADR-018 در هر درخواست: 401 برای session revoke/منقضی و user حذف‌شده، 403 برای inactive/blocked | `test_auth_permissions.py`: `test_access_token_dies_with_its_session`، `..._of_a_rotated_session_...`، `test_expired_session_is_unauthorized`، `test_soft_deleted_user_is_unauthorized`، `test_inactive_or_blocked_user_is_forbidden_on_every_request` |
| ADR-018 permission فقط از DB؛ نقش ارسالی کلاینت بی‌اثر | `test_permission_matrix_for_every_role`، `test_client_supplied_role_or_permission_is_ignored`، `test_role_change_takes_effect_without_a_new_token` |
| ADR-018 `/admin` بدون token → 401 و بدون نقش مدیریتی → 403 | `test_auth_security.py::test_every_admin_route_requires_authentication`، `::test_customer_is_forbidden_on_every_admin_route` |
| ADR-018 مالکیت (customer فقط داده خودش) | `test_auth_security.py::test_customer_sees_and_edits_only_their_own_account`، `test_auth_dependencies.py::test_ensure_owner_hides_foreign_or_unowned_resources_as_not_found` |
| ADR-019 admin نقش نمی‌دهد (نه به super_admin، نه به خودش) | `test_admin_users.py::test_admin_cannot_change_roles`، `test_role_change_forbidden_for_other_roles` |
| ADR-019 audit تغییر نقش و وضعیت | `test_super_admin_replaces_roles_with_audit`، `test_admin_deactivates_customer_and_revokes_all_sessions`، `test_reactivation_keeps_sessions_revoked_and_is_audited` |

## پوشش کدهای وضعیت
| کد | نمونه تست |
|---|---|
| 400 | `test_list_users_rejects_invalid_or_unknown_parameters`، `test_role_change_accepts_only_default_roles`، `test_request_otp_rejects_invalid_body`، `test_patch_rejects_system_fields` |
| 401 | `test_every_admin_route_requires_authentication`، `test_expired_code_is_rejected`، `test_refresh_after_logout_is_unauthorized` |
| 403 | `test_customer_is_forbidden_on_every_admin_route`، `test_admin_cannot_change_status_of_staff`، `test_admin_cannot_change_roles` |
| 404 | `test_status_change_unknown_or_deleted_user_is_not_found`، `test_role_change_unknown_or_deleted_user_is_not_found` |
| 409 | `test_last_super_admin_cannot_be_demoted_or_deactivated` |
| 422 | `test_status_change_of_self_is_rejected`، `test_role_change_of_self_is_rejected` |
| 429 | `test_request_otp_per_mobile_limit_returns_429` و بقیه تست‌های 429 در ADR-016 |
