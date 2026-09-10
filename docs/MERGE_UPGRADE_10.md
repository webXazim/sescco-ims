# Merge Upgrade 10 — Unified application shell

Upgrade 10 completes the user-facing merge boundary between Inventory Management and Payroll Management.
Both areas use the same authenticated `accounts.User`, active `core.Company`, and `CompanyMembership`.

The shared switcher hierarchy is Business → Area → module-specific navigation. Inventory keeps its existing
server-rendered navigation and Payroll keeps its DocGen V2 Internal/Rental/Management navigation. This avoids
rewriting stable application behavior merely to share navigation chrome.

Company switches are server-authorized. The current area is retained only when the destination membership can
open it; otherwise the unified home resolver chooses a permitted area. Detail URLs are never carried across
companies.

No database migration is introduced by Upgrade 10. Production preflight verifies the shared template/assets via:

```bash
bash scripts/verify-platform-shell.sh
```
