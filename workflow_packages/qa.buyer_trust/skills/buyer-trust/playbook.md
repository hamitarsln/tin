# Buyer-trust fix playbook

Copy-paste starters for the fixes GATE.md names. Repository changes go to `site.health_improve`
through the hand-off blocks, which point at these starters; host settings, policy text and
decisions stay with the founder. Prefer the smallest safe change. Do not paste secrets.

## Security headers

Static hosts (`_headers`, `vercel.json`, `netlify.toml`, or reverse proxy):

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
X-Content-Type-Options: nosniff
```

Starter Content-Security-Policy. Tighten `script-src` and `connect-src` to the hosts the site actually uses:

```
Content-Security-Policy: default-src 'self'; img-src 'self' https: data:; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'
```

Next.js (`next.config.js` headers) or Express (`helmet`) can emit the same values. Verify with one safe GET and record the exact response headers.

## security.txt

Serve at `/.well-known/security.txt` with `Content-Type: text/plain`:

```
Contact: mailto:security@example.com
Expires: 2027-01-01T00:00:00Z
Preferred-Languages: en
```

Use the contact the site already publishes and an expiry about a year out. Keep it to contact plus
expiry unless a policy URL already exists. Choosing a security contact is the founder's call.

## Founder-owned fixes

These are decisions or policy text, so no workflow makes them:

- Plain-http redirect: enable "force HTTPS" or the equivalent redirect in the host settings.
- Privacy and Terms: publish both, then link them in the footer of every page, including checkout.
- Contact: a real address or monitored inbox, with a response expectation, within one click of
  pricing or checkout.
- Refunds or cancellation: state the terms the business actually offers and link them within one
  click of checkout. Match the Feature map; never promise terms the founder has not chosen.
- Total before pay and guest checkout: checkout and pricing decisions.
- `/.git/HEAD` or `/.env` returning 200: block the path at the host today. A 200 may be an HTML
  app fallback; it does not prove file or secret exposure. If a file was served, rotate every
  secret it held, out of band. Treat the path response as Fix now.

## What this playbook is not

No CVE database, no dependency scan, no intrusive prober. For full CVE management use Dependabot, Snyk, or the platform patch channel. Never invent CVEs, versions, or exploitability.
