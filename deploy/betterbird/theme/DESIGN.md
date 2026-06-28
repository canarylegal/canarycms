# Canary theme for Betterbird — design spec

Visual language aligned with the Canary web app (`frontend/src/index.css`, `theme.ts`).

## Palette

| Token | Hex | Use |
|-------|-----|-----|
| **Navy (page chrome)** | `#1e3a8a` | Main window background, tab strip, mail/calendar chrome |
| **Navy deep** | `#1e40af` | Hover on chrome, inactive tabs |
| **Accent blue** | `#2563eb` | Selected tab indicator, primary buttons, links, unread emphasis |
| **Accent light** | `#dbeafe` | Subtle highlights, add-on panels |
| **Panel white** | `#ffffff` | Message list cards, reading pane, dialogs |
| **Panel soft** | `#f8fafc` | Alternate rows, nested surfaces |
| **Text** | `#0f172a` | Body text on white |
| **Text on navy** | `#f8fafc` | Tab labels, toolbar icons on navy |
| **Muted** | `#64748b` | Secondary labels, read mail |
| **Border** | `rgba(15, 23, 42, 0.1)` | Dividers on white panels |
| **Canary gold** (accent only) | `#facc15` | Optional star/unread dot — use sparingly |

## Typography

- **UI:** system stack (Segoe UI / Roboto on Windows, system-ui on Linux) — Betterbird does not ship DM Sans.
- **Density:** default Betterbird spacing; theme does not shrink lists.

## Layout intent

```
┌──────────────────────────────────────────────────────────────┐
│  NAVY: tab bar (white text) · selected tab = white panel     │
├──────────────┬───────────────────────────────────────────────┤
│  folder pane │  WHITE: message list / calendar grid          │
│  (soft grey  │  · unread subject = accent blue               │
│   on white)  │  · selected row = light blue wash             │
├──────────────┴───────────────────────────────────────────────┤
│  WHITE: reading pane / event detail                          │
└──────────────────────────────────────────────────────────────┘
```

## Scope

| Styled | Not styled |
|--------|------------|
| Window + tab chrome | Compose HTML body (web content) |
| Folder tree + message cards | External web pages in browser tab |
| Calendar month grid chrome | Every third-party dialog |
| Primary buttons in chrome | Canary add-in panels (already use `canary-theme.css`) |

## Deployment options

1. **`userChrome.css`** (this folder) — per-profile; best for pilot + IT script.
2. **`policies.json`** — enable `toolkit.legacyUserProfileCustomizations.stylesheets` (see README).
3. **Future:** signed lightweight “Canary Theme” WebExtension if you want one-click install without profile files.
