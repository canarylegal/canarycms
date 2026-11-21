# Product UI theme

The current frontend theme has one entry point:

- `frontend/src/canary-theme.css` imports the base and surface layers.
- `frontend/src/index.css` owns root tokens, shared components, typography and accessibility baselines.
- `frontend/src/local-modern.css` provides surface styling and may override chrome-pack variables only.

Brand defaults are DM Sans, Canary yellow primary (`#f0d010`) and dark text on primary buttons. Signature fonts are served from `/canary-fonts/`; `/fonts` is reserved for ONLYOFFICE in the production proxy.

From `frontend/`, run `npm test`, `npm run test:outlook`, `npm run lint:ci` and `npm run build` after changes. Use `npm run dev` only in a local development environment. These commands do not authorize a live deployment.

Use the [recorded deployment procedure](REPRODUCIBLE_DEPLOYMENTS.md) for any separately authorized update of an existing installation. Do not use machine-specific paths or one-off service rebuild scripts.
