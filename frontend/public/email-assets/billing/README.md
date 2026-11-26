# Billing email artwork — versioned publication verified

On 27 October 2026, the separately approved scope published and verified three new objects in Saiia-dev (`rbmxfazjbldmkomdpyzl`), public `email-assets`: `payment-success-20261027-v1.jpg`, `renewal-success-20261027-v1.jpg`, `mascot-20261027-v1.png`. Local source filenames below remain unchanged. No existing object was overwritten. `manifest.json` records exact public URLs/hashes; see `docs/C12_EMAIL_REDESIGN_01_EXECUTION.md` for actual counters and inbox evidence.

| File | Dimensions | Bytes | Provenance |
| --- | --- | --- | --- |
| `payment-success.jpg` | 1080 × 540 | 56,965 | Owner-supplied `Robot Celebrates Payment Received-1.png` |
| `renewal-success.jpg` | 1080 × 540 | 63,394 | Owner-supplied `Robot Mascot with Renewal Calendar-2.png` |
| `mascot.png` | 120 × 80 | 11,659 | Exact existing `src/assets/startup-login/login-mascot.png`, resized without crop/replacement |

The heroes retain the supplied compositions and colors. Only resolution and compression were changed. No generated replacement character, reset-password illustration, text, prices, dates, logos or buttons were added to either hero. `manifest.json` records source names, dimensions and hashes.

The isolated check used `EMAIL_ASSET_BASE_URL=https://rbmxfazjbldmkomdpyzl.supabase.co/storage/v1/object/public/email-assets` with the versioned template filenames. It remains unset by default outside that process; no production configuration was activated. Auth assets/bucket settings/DNS were unchanged. Published assets are retained for delivered emails. README/manifest were not uploaded. Future image changes require new versioned names and authorization, never overwrite these objects.

Header is rendered at 48 × 32; heroes at up to 540 × 270. Hero alt text is descriptive; essential receipt content is live text and remains readable when images fail. Deployment/caching and a later inbox check require separate authorization.
