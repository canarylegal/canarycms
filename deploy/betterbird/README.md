# Betterbird enterprise policy

Cross-platform `policies.json` for firm-managed Betterbird workstations:

- Force-install **Canary — file to matter** add-on
- Block all other add-ons
- Require a **primary password**
- Replace default calendar categories with the three firm labels (names and colours match Canary)

Category names and colours were taken from a sample Betterbird profile on Colin’s machine (May 2026).

## Deploy paths

| OS | Path |
|----|------|
| **Linux (Kubuntu)** | `/etc/thunderbird/policies/policies.json` |
| **Windows** | `C:\Program Files\Betterbird\distribution\policies.json` |

Create the `policies` or `distribution` directory if it does not exist. Use the **official Betterbird installer** (not Flatpak).

### Linux (this machine)

```bash
sudo mkdir -p /etc/thunderbird/policies
sudo cp deploy/betterbird/policies.json /etc/thunderbird/policies/policies.json
```

Restart Betterbird. On first launch after policy install, users set the primary password when prompted.

### Windows

Copy `policies.json` to `C:\Program Files\Betterbird\distribution\` during imaging or via Intune/GPO/startup script (elevated).

## Calendar colours in Betterbird

Betterbird colours CalDAV events by **category name** when:

1. The event iCal contains `CATEGORIES:<label>` (written by Canary when a calendar label is set), and  
2. The category exists in this policy with a matching colour.

Category strings must match **exactly** (including spaces around `/` in `Funds / Statement Requested`).

## Canary server side

Set in the firm `.env` (not committed):

```bash
CANARY_CALENDAR_LABEL_SPECS=[{"name":"Funds / Statement Requested","color":"#2563EB"},{"name":"Exchanged","color":"#F8E45C"},{"name":"Completed","color":"#33D17A"}]
```

Optional: `CANARY_SYNC_CALDAV_EVENT_CATEGORIES=0` disables one-time startup sync of existing labelled events to CalDAV.

After changing `.env`, restart the backend. Labels are created on each user calendar at startup; new events pick up `CATEGORIES` automatically.

## Updating the add-on URL

When releasing a new signed `.xpi`, bump `install_url` in `policies.json` to match the version on `https://canarylegalsoftware.co.uk/thunderbird/`. Existing installs still auto-update via `updates.json` once the add-on is installed.
