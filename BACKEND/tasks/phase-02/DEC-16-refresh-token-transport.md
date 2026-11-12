# DEC-16 — Token transport (D16)

**Status:** COMPLETE · **Priority:** HIGH · **Estimate:** 0.5h (estimate) · **Deadline:** — · **Dependencies:** — · **Level:** HIGH

## Objective
روش تحویل access و refresh token.

## PRD reference
«هویت و دسترسی»

## Acceptance Criteria
- [x] فقط وب: refresh در cookie `HttpOnly; Secure; SameSite=Strict` با Path محدود به auth؛ access در body.
- [x] token service مستقل از transport.
- [x] ADR-012 ثبت شد و PRD «هویت و دسترسی» به‌روز شد.

## Implementation Notes
کاربر `Path=/auth` گفت؛ چون routeها زیر `/api/v1` هستند، مقدار عملی `Path=/api/v1/auth` است (در ADR-012 ثبت شد).

## Validation
—

## Log
- 2026-09-29: تصمیم کاربر → ADR-012.
