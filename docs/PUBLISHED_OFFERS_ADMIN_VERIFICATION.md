# Published offers admin verification

Verified locally on 2026-10-23. This change adds offer discovery to the existing subscription workspace; it does not activate production publication.

## Use

Open `/auth/admin/subscriptions` and find **Published offers**. Choose **Open offer** to inspect existing published terms, or **Create draft version** to load a separate unsaved editable version. Save, preview and review remain explicit existing actions. **Refresh offers** reloads the list. The existing unsaved-edit confirmation remains mandatory when replacing local edits.

The list reads `/api/catalog` from the admin workspace's configured backend, then uses the existing protected offer-read endpoint. It deliberately does not use a different environment's localhost pricing-preview proxy. Current permissions still govern protected reads and all writes.

Only currently visible published offers are discoverable through this existing read contract. Scheduled, expired and retired versions require the existing **Open an offer by ID** control. An unavailable catalog is distinct from an empty catalog. A normal backend without public catalog composition will report unavailable; this UI does not enable that composition or fall back to demo records.

## Evidence

- Playwright workspace and lifecycle regression suite: **52 passed**.
- Focused catalog, lifecycle, proxy and money checks: **14 passed**.
- Frontend production build: passed; existing chunk-size warning remains.
- Real isolated demo browser flow: synthetic JWT authentication, native PostgreSQL-backed catalog and protected Plus read, local successor draft creation, Close, ordinary-account 404. **Zero browser API writes**; no offers were changed by this verification.
- Mobile width 390px: no horizontal overflow. Desktop capture: 1366px.
- Graphify queried before and after the change; whitespace check passed.

Re-run the browser integration while the isolated demo is running:

```powershell
cd frontend
node tests/catalog/published-offers.integration.mjs
```

Isolated entry: `http://127.0.0.1:5187/__demo/as/admin`. Normal authentication and services remain separate.

Screenshots: [desktop](../tmp/subscription-demo/published-offers-desktop.png), [mobile](../tmp/subscription-demo/published-offers-mobile.png).

No backend routes, SQL migrations, grants, shared database writes, payment/provider calls or Electron changes are part of this change.
