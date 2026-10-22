# ADR 007 — SSRF protection for outbound webhooks

- **Status:** Accepted (2026-10-22)

## Context

Customers type webhook URLs into the dashboard and the server then makes HTTP requests to them: on every
extraction result, and on demand through the "ping" endpoint. Nothing restricted the destination, so a
customer (or anyone with an account) could register URLs such as:

- `http://169.254.169.254/latest/meta-data/` — the cloud metadata service, which holds credentials;
- `http://localhost:5432` or `http://10.x.x.x/...` — databases and admin tools on the private network.

That is **Server-Side Request Forgery (SSRF)**: the attacker cannot reach those systems, but our server can,
and we made the request for them. It was a *full-read* variant, not just blind: the ping endpoint returned
the target's response body (up to 500 chars) and delivery history stored up to 2 KB of it.

## Decision

`app/core/url_safety.py` is the single gate for every outbound request to a customer-supplied URL.

1. **Allow-list by address, not by text.** Only `http`/`https`, no `user:pass@`. The hostname is *resolved*
   and every resulting address must be public: private, loopback, link-local (including metadata),
   CGNAT, multicast, reserved and unspecified ranges are refused. Resolving first also defeats numeric
   disguises (`http://2130706433/`, `http://0x7f.0.0.1/`, `::ffff:127.0.0.1`). If a host resolves to several
   addresses, one bad record blocks it.
2. **Checked at save time and again at use time.** Create/update returns `422` with a plain message. Every
   delivery and ping re-validates, so rows saved before this change, or whose DNS changed later, are
   refused too. A host that does not resolve yet is accepted at save time (DNS may not be set up) and
   still fails safely at delivery.
3. **Connect to the validated IP.** `safe_post` sends the request to the address that was checked, with the
   original `Host` header and TLS server name preserved, so the DNS answer cannot change between the check
   and the connection (DNS rebinding). If an address cannot be connected to (e.g. IPv6 with no route), the
   next *validated* address is tried, up to 3, like a browser would; only connection failures fall through, never
   a timeout mid-request (it could duplicate a delivery). Redirects are never followed (a redirect to an internal host is the
   classic bypass).
4. **Blocked requests are never sent and never echo anything.** Ping returns a fixed refusal message;
   a blocked delivery is recorded as `Blocked: ...` with no response body and counts toward the existing
   auto-disable threshold.
5. **Local development opt-out:** `WEBHOOK_ALLOW_PRIVATE_HOSTS=true` (default `false`) allows private
   destinations. Must stay off in production.

## Consequences

- Webhooks pointing at `localhost` or private IPs stop working unless the opt-out is set (intended).
- This is application-level defence. **Production should also restrict egress at the network layer**
  (security group / egress proxy) so a future bug cannot reopen the hole. Tracked as a backlog item.
- Addresses that merely *carry* an IPv4 address (IPv4-mapped `::ffff:`, NAT64 `64:ff9b::/96`, 6to4 `2002::/16`)
  are judged by the embedded IPv4. This matters in both directions: it stops `64:ff9b::a9fe:a9fe` (the metadata
  address) and also avoids falsely blocking every IPv4-only public site on DNS64/NAT64 networks.
- Inbound webhook adapters are unaffected: they receive requests, they do not make them.

## Alternatives considered

- **Block by hostname/regex only.** Trivially bypassed (decimal/hex IPs, DNS names pointing at internal IPs).
- **Validate once at save time.** Misses DNS changes and rows that already exist.
- **A custom network backend for httpx.** Would also pin the IP, but depends on private httpx/httpcore
  internals; pinning via the request URL + `Host` + `sni_hostname` uses only public API.
