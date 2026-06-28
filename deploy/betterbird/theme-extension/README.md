# Canary theme for Betterbird (WebExtension)

Official Betterbird themes install as **add-ons**, not via Config Editor.

## Install (recommended)

1. Build or use the pre-built XPI:
   ```bash
   node deploy/betterbird/theme-extension/package.mjs
   ```
2. Betterbird → **Settings** → **Add-ons and Themes**
3. Gear menu → **Install Add-on From File…**
4. Select `deploy/betterbird/theme-extension/dist/canary-theme-1.2.0.xpi`
5. When prompted, **enable** the theme (Add-ons → Themes → Enable)

Themes do **not** need Mozilla signing for local “Install from file” (unlike the Canary mail add-on).

## Enterprise (optional)

If `policies.json` blocks all add-ons except Canary, **whitelist this theme** in `ExtensionSettings`:

```json
"canary-theme@canarylegal.co.uk": {
  "installation_mode": "force_installed",
  "install_url": "https://your-host/thunderbird/canary-theme-1.0.0.xpi"
}
```

Host the `.xpi` on HTTPS alongside the mail add-on, or copy via imaging.

## Colours

| Key | Hex | Role |
|-----|-----|------|
| frame / toolbar | `#1e3a8a` | Navy chrome |
| tab_line / icons_attention | `#2563eb` | Accent |
| tab_selected / toolbar_field | `#ffffff` | Content surfaces |
| tab_text / popup_text | `#0f172a` | Body text |

Full design notes: [../theme/DESIGN.md](../theme/DESIGN.md)

## Advanced: userChrome.css

The [userChrome.css](../theme/userChrome.css) path can style message cards and calendar grids more deeply, but requires `toolkit.legacyUserProfileCustomizations.stylesheets` (Config Editor — may be hidden in some Betterbird builds). **Use the XPI theme first**; add userChrome only if you need finer control.
