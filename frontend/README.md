# Canary CMS frontend

React, TypeScript and Vite frontend for the current CMS line. Use the Node version pinned in the Dockerfile/workflow and install the lockfile with `npm ci`.

```sh
npm test
npm run test:outlook
npm run lint:ci
npm run build
```

`npm run dev` starts the local Vite server. See [troubleshooting](../docs/TROUBLESHOOTING.md) for the local API proxy and [UI theme ownership](../docs/UI_THEME.md) before editing theme styles.

The Outlook add-in source is maintained in [canary-outlook](https://github.com/canarylegal/canary-outlook). This frontend stages its checksum-pinned vendor bundle before development/build and verifies the hosted output afterward. Generated public/outlook-addin files are not editable source. Thunderbird is maintained in [canary-thunderbird](https://github.com/canarylegal/canary-thunderbird) and is not bundled here.

Lint has a tracked warning baseline; passing it does not mean zero warnings. For authorized deployments, use the [reproducible deployment guide](../docs/REPRODUCIBLE_DEPLOYMENTS.md), not a local development server.
