# Alerts runbook (OPS-02)

Written for: whoever is on call for the API once production exists (D13).

The rules are in `ops/prometheus/alerts.yml`. Prometheus scrapes `GET /metrics` with `Authorization: Bearer <METRICS_TOKEN>`. Each section below matches one alert name. Every log line carries `request_id`, so start from the logs of the time window.

## ApiHigh5xxRate

**Means:** more than 2% of responses were 5xx for 10 minutes.

1. Find the routes on `http_requests_total{status=~"5.."}`.
2. Search the logs for `unhandled.exception` and `error.reported`. They carry the error type and route.
3. If it started with a deploy, roll back to the previous image tag.

## PaymentGatewayUnavailable

**Means:** payment endpoints answered 503 `PAYMENT_GATEWAY_UNAVAILABLE`, so the gateway did not respond.

Orders keep their 15-minute reservation and callbacks are retried. The reconciliation job settles lost callbacks later. Check the gateway's status page. If the outage is long, tell support that customers may see "try again".

## PaymentReconcileStalled

**Means:** `payment_reconcile` has had no successful round for 15 minutes. Lost callbacks are not being settled.

1. Look for `payment.reconcile_round_failed` in the logs.
2. Check `database_up`.
3. Restarting the API restarts the job. In production the API refuses to start without a real gateway (ADR-058).

## ReservationSweepStalled

**Means:** `reservation_sweep` has had no successful round for 15 minutes.

Expired reservations still free their stock lazily on the next read (ADR-036), so this is not urgent. Look for `reservation.sweep_round_failed` in the logs.

## RefundRequiredWaiting

**Means:** at least one payment has been in `refund_required` for over 24 hours. The customer paid, but there is no valid order for the payment.

An admin with `payments:refund` refunds the customer at the bank or gateway. They then record it with `POST /admin/payments/{id}/refund` (ADM-08).

## DatabaseDown

**Means:** the API could not run `SELECT 1` for 2 minutes.

1. Check the `postgres` container and the host's disk.
2. Never delete the `postgres_data` volume.
3. If the data is damaged, follow `docs/ops/BACKUP-RESTORE.md`.

## MetricsScrapeFailing

**Means:** Prometheus cannot read `/metrics`.

`/metrics` answers 404 for a missing or wrong token. Check that `METRICS_TOKEN` in the API's environment matches the scrape configuration, and that the API is up (`/health`).
