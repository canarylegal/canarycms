# Outlook add-in — Microsoft 365 deployment and troubleshooting

Source, manifest template and add-in-specific build instructions live in [canary-outlook](https://github.com/canarylegal/canary-outlook). Canary CMS hosts a pinned bundle on its existing HTTPS origin; see [the hosting contract](DEPLOYMENT.md#outlook-source-ownership-and-hosting-bundle).

## Manifest and assets

There is one supported manifest: `https://YOUR_HOST/outlook-addin/manifest.xml`. It includes the configured read/compose commands and send event. Do not use the retired `manifest-minimal.xml` or `manifest-with-send.xml` URLs; those files are not shipped.

Before any authorized Microsoft 365 installation or update, verify:

- The manifest returns XML and uses the intended HTTPS origin, identity and version.
- Task panes, commands and `/outlook-addin/auth-callback.html` return real files, not the SPA fallback.
- Required icons are under `/icons/`: `icon16.png`, `icon32.png`, `icon64.png`, `icon80.png` and `icon128.png`.
- `/.well-known/microsoft-officeaddins-allowed.json` uses the same origin.
- The manifest passes the Microsoft validator and the intended Outlook clients have been tested with synthetic mail.

The same manifest is the input for supported user sideloading or administrator-managed deployment. Use your tenant's current Integrated apps workflow and assignment policy. Preserve existing origin and add-in identity when updating an installation; do not remove established assignments merely to troubleshoot visibility.

## If an add-in is installed but not visible

Open a message in the intended read or compose mode and check Apps and the relevant ribbon commands. Record the Outlook client/build, manifest version, assigned user and whether the problem occurs in both Outlook on the web and desktop.

Have the tenant administrator inspect assignment status, supported activation contexts, mailbox policy and Office add-in permissions. A missing command alone does not prove a tenant-wide sideload restriction. Avoid changing tenant-wide policy until the cause is established. Refer to [Microsoft's Outlook add-in documentation](https://learn.microsoft.com/office/dev/add-ins/outlook/) for the current client and deployment requirements.

## Sign-in and filing checks

Use synthetic mail in an isolated test mailbox. Verify Connect to Canary, callback completion, matter search, filing, compose attachments and send-time filing in each intended client. Native Outlook/Microsoft 365 testing is still outstanding; the completed browser checks use synthetic Office APIs.

Keep access to these existing routes:

- `/outlook-addin/*`
- `/icons/*` for the manifest's required images
- `/.well-known/microsoft-officeaddins-allowed.json`
- `/connect/mail-plugin` and the required `/api/*` endpoints

Do not change hosting URLs, register another add-in, enable jobs or deploy merely to validate documentation changes.
