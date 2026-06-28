# Betterbird (Canary)

Optional Betterbird styling and enterprise deployment notes for firm-managed workstations.

## Canary UI theme

Navy/white chrome matching the Canary web app.

**Install:** Settings → Add-ons and Themes → Install Add-on From File → `theme-extension/dist/canary-theme-1.2.0.xpi` (build: `node theme-extension/package.mjs`). Enable under **Themes**. v1.2 fixes spaces-sidebar icons and the reading-pane logo watermark.

Optional deeper styling: run `theme/install-theme.sh` — copies `userChrome.css` + logo and enables the legacy stylesheet pref.

See [theme/README.md](./theme/README.md) and [theme-extension/README.md](./theme-extension/README.md).

## Enterprise policy (`policies.json`)

Firm-specific `policies.json` files (force-installed add-ons, calendar category colours, primary password, etc.) are **not** stored in this repository. Maintain them locally or in your deployment tooling.

Typical install paths:

| OS | Path |
|----|------|
| **Linux** | `/etc/thunderbird/policies/policies.json` |
| **Windows** | `C:\Program Files\Betterbird\distribution\policies.json` |

Use the official Betterbird installer (not Flatpak). Restart Betterbird after deploying policy.

When releasing a new signed mail add-on `.xpi`, update the firm's `install_url` to match the version on your hosting server. Existing installs still auto-update via `updates.json` once installed.

## Calendar category colours

Betterbird colours CalDAV events by **category name** when the event iCal contains `CATEGORIES:<label>` and the category exists in policy with a matching colour. Category strings must match exactly.

On the Canary server, set label specs in the firm `.env` (not committed), e.g. `CANARY_CALENDAR_LABEL_SPECS=[{"name":"…","color":"#…"}]`. Restart the backend after changes.
