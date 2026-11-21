# Canary theme for Thunderbird

Navy chrome + white panels + blue accents — matches the Canary web app.

## Install (recommended): theme add-on (.xpi)

Thunderbird themes install like any other add-on:

1. **Settings → Add-ons and Themes →** gear menu → **Install Add-on From File…**
2. Choose **`canary-theme-1.2.0.xpi`** (build with `node deploy/thunderbird/theme-extension/package.mjs` from the repository root).
3. Open the **Themes** tab and **Enable** “Canary”.

Use the reviewed theme package; the separate Canary mail add-on has its own distribution instructions.

See [theme-extension/README.md](../theme-extension/README.md) for enterprise force-install via `policies.json`.

## Optional: deeper styling (userChrome.css)

For message-card colours, calendar tweaks, etc., see [theme/userChrome.css](./userChrome.css). That path needs `toolkit.legacyUserProfileCustomizations.stylesheets = true` in **about:config** (not always exposed under Settings). Most users should use the **XPI theme** only.

Design spec: [theme/DESIGN.md](./DESIGN.md)
