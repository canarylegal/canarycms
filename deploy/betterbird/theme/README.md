# Canary theme for Betterbird

Navy chrome + white panels + blue accents — matches the Canary web app.

## Install (recommended): theme add-on (.xpi)

Betterbird themes install like any other add-on:

1. **Settings → Add-ons and Themes →** gear menu → **Install Add-on From File…**
2. Choose **`canary-theme-1.2.0.xpi`** (build with `node theme-extension/package.mjs`, or use the copy in Downloads).
3. Open the **Themes** tab and **Enable** “Canary”.

Themes do **not** need Mozilla signing for local install (unlike the Canary mail add-on).

See [theme-extension/README.md](./theme-extension/README.md) for enterprise force-install via `policies.json`.

## Optional: deeper styling (userChrome.css)

For message-card colours, calendar tweaks, etc., see [theme/userChrome.css](./theme/userChrome.css). That path needs `toolkit.legacyUserProfileCustomizations.stylesheets = true` in **about:config** (not always exposed under Settings). Most users should use the **XPI theme** only.

Design spec: [theme/DESIGN.md](./theme/DESIGN.md)
