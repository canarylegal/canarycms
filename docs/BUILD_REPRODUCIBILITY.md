# Pinned build inputs

The supported, verified build target is **Linux amd64 / CPython 3.12.13**. Dockerfiles and Compose infrastructure images use repository digests, not just mutable tags. CI actions use commit SHAs; CI Python and Node versions match the container toolchains. The frontend uses its committed npm lockfile and `npm ci` in both development and production builds.

Backend builds use:

- `requirements.txt`: intended direct application dependencies.
- `requirements.lock`: exact direct and transitive versions with SHA-256 hashes of accepted PyPI archives.
- `build-requirements.in` and `build-requirements.lock`: pinned pip, setuptools, wheel and packaging.
- `--require-hashes --no-build-isolation`: source distributions cannot silently install an unpinned build toolchain.
- `debian.sources`: signed Debian/security snapshots fixed at `20261119T000000Z`, with explicit git and CA package versions. Expired snapshot metadata is allowed; signature validation remains enabled.

`GIT_COMMIT` is applied after dependency installation so changing a source revision does not invalidate the dependency layers. `scripts/check_build_pins.py` rejects mutable image/action references and direct requirements changes without a regenerated lock. `pip check` runs during image construction and backend CI.

## Updating dependencies deliberately

1. Change the intended versions in `backend/requirements.txt` or `backend/build-requirements.in`.
2. In a fresh container using the pinned Python base, install the pinned build tools, then resolve the intended application requirements. Export the resulting environment with `python -m pip freeze` to a temporary file. Do not freeze a developer's unrelated environment.
3. Generate the archive hashes with:

   ```sh
   python3 scripts/lock_python.py /tmp/resolved-runtime.txt backend/requirements.lock --direct backend/requirements.txt
   python3 scripts/lock_python.py backend/build-requirements.in backend/build-requirements.lock --direct backend/build-requirements.in
   python3 scripts/check_build_pins.py
   ```

4. Review all changed transitive versions and hashes. Build from scratch, run backend tests and `make test-core-workflows`, then repeat the recovery drill before promoting the new image IDs.
5. For OS/base-image updates, resolve and review the new registry digests, update the Debian snapshot/package pins together, and run the same checks. Digest references are an update mechanism, not a substitute for security updates.

The initial runtime lock captures the versions in the previously deployed image; it is not an opportunistic dependency upgrade. The lock generator obtains hashes from the exact-version PyPI metadata and refuses unversioned/direct-URL requirements.

## What is and is not reproducible

These changes fix dependency versions and artifact inputs. Docker layer timestamps and locally built source-distribution wheel metadata can still differ between builds; bit-identical image digests are not claimed. Deploy and rollback the **recorded built image IDs**, not a fresh rebuild assumed to be identical.

Keep built images in a retained registry or an image archive, alongside source revision, locks, resolved private configuration, decryption keys and optional-package snapshots. Registry/PyPI/Debian snapshot availability is still needed for a fresh online build. The restore drill uses prebuilt images and does not need outbound network access.

Commercial/firm packages are separate artifacts. Preserve their exact source/bundle snapshot and manifest with the release; core dependency locks do not version an external bind-mounted package. Recovery records hashes for the copied optional package.
