# Subscription review popup verification

23 October 2026. Frontend presentation only; local acceptance, not deployment approval.

## Meaning and implementation

The former side panel was the **Draft preview**, opened by **Preview saved draft**. Publication approval is the separate **Review for publication** action. Both now use a centered **Subscription review** popup while preserving their different operations. The duplicate side panel is removed.

Customer preview still calls the existing structural preview endpoint. Publication review still obtains the exact saved-revision basis, then requires **Confirm review** to create its receipt. **Publish reviewed offer** / **Replace reviewed offer** still opens a separate explicit confirmation state; the same dialog surface changes state, rather than opening overlapping dialogs. Retire confirmation also retains its existing authorization sequence.

The new small reusable native dialog follows `WebsiteSessionViewer`'s white surface, rounded border, close icon, dim backdrop, inert background and scroll/focus restoration approach. Transcript code/styles were not edited. The popup header stays visible while its body scrolls. It has an accessible name, aria-modal, contained Tab/Shift+Tab focus, Escape and **Close subscription review** x. It locks/restores body and root scrolling and returns focus to the trigger when available.

Closing only changes visibility. It does not abort requests, discard drafts, erase receipts, generate retry identities or publish. **Open subscription review** reopens retained publication-review/recovery state without automatically sending a mutation. Existing pending keys and Check/Retry actions remain available. Draft/revision/dirty changes invalidate existing review binding, and account loss/unmount clears private state. Late closed-preview responses may cache their current draft's result but cannot reopen the popup; epoch/sequence guards prevent cross-draft/account adoption.

Permission denial continues the existing private-state cleanup/404 behavior, rather than preserving protected terms inside an unauthorized popup. Other safe validation, policy/storage-unavailable and stale/expired messages are displayed within the review popup. Requirement buttons in customer preview close it before focusing an editor field.

## Files

- `frontend/src/auth/SubscriptionReviewModal.jsx`: native dialog/focus/scroll behavior.
- `frontend/src/auth/SubscriptionAdmin.jsx`: customer preview moved intact out of the aside; editor spans the available width.
- `frontend/src/auth/CatalogLifecycle.jsx`: visible publication-review/loading/error/recovery state and unchanged explicit mutation sequence.
- `frontend/src/auth/subscription-admin.css`: matching modal appearance, fixed header and responsive internal scroll area.
- Existing workspace/lifecycle and native integration browser scripts updated to explicitly close the now-modal customer preview and use the review dialog's accessible name. No functional assertions or timeout budgets were weakened.
- `docs/SUBSCRIPTION_ADMIN_USER_GUIDE.md`: current popup instructions.

## Actual checks

- **47 passed**: workspace/lifecycle Playwright regression suite. New checks cover centered desktop/mobile bounds, no duplicate aside, focus containment/restoration, scroll lock, close/reopen, loading/unavailable states, late response isolation, pending receipt identity, explicit publication confirmation, expired review and logout during a pending review. API/session responses in this suite are isolated fixtures.
- Additional targeted pending-review/focus-restoration check passed after retaining the reopen trigger in the DOM.
- **14 passed**: existing Node catalog/draft/lifecycle/money/proxy checks.
- **1 native browser runner passed** (`test_free_browser_native.py`, PostgreSQL **17.11**): import/save/reopen/edit/customer-preview/Close with actual JWT, service, adapter and restricted native database connections. Synthetic browser session source and loopback transport; no deployed Supabase claim.
- `lifecycle.ist.integration.mjs` passed against the running isolated demo: browser in Los Angeles timezone, actual JWT/API/native SQL policy preview, correct current terms and IST confirmation, invalid end ordering blocked, no publication. Three main public offers remained intact.
- Production build passed with its existing chunk-size advisory. Whitespace checked. Graphify queried before edits and targeted code graph queried afterward.

Actual isolated browser captures at **1366 x 768** and **390 x 844**:

- [Desktop popup](../tmp/subscription-demo/subscription-review-desktop.png)
- [Mobile popup](../tmp/subscription-demo/subscription-review-mobile.png)

No backend contracts, shared migrations, permissions, real offers, pricing, Electron, payment/admission settings or Transcript behavior changed. Synthetic unpublished drafts were used for native preview verification. Production configuration/policy prerequisites remain unchanged.
