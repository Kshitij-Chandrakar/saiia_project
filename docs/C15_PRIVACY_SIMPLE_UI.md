# C15 privacy controls: simplified local UI

The Settings page now starts with three plain-language choices: download data, manage interview history, or delete the account. Existing export, session/history erasure, reauthentication, typed confirmation, expiry and status APIs are unchanged.

Long policy explanations are behind three accessible disclosures (stored data, retained data, and devices/providers). Controls remain visible, disabled honestly while activation is off, and no deletion was executed during verification.

Verification: frontend production build passed; local browser smoke passed against the loopback demo (`/auth/settings`, profile bootstrap 200, deletion dialog opened, Super-admin login, no deletion submission). The local API key lifetime repair remains enabled for the disposable demo only.

Production Auth/Storage/provider acceptance, physical device cleanup, and real deletion remain outside this local UI change.
