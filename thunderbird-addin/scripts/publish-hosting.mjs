import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  ADDON_ID,
  UPDATE_BASE_URL,
  buildUpdatesManifest,
  updatesJsonPublicUrl,
} from './hosting-config.mjs'

const addinRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), '..')
const manifest = JSON.parse(fs.readFileSync(path.join(addinRoot, 'manifest.json'), 'utf8'))
const version = manifest.version
const artifactDirs = [
  process.env.CANARY_TB_ARTIFACTS_DIR,
  path.join(addinRoot, '.build-out'),
  path.join(addinRoot, 'dist'),
].filter(Boolean)

const hostingDir = path.join(addinRoot, 'hosting')

function findSignedXpi() {
  for (const dir of artifactDirs) {
    if (!fs.existsSync(dir)) continue
    const matches = fs.readdirSync(dir).filter((name) => name.endsWith('.xpi'))
    if (matches.length === 0) continue
    matches.sort()
    return path.join(dir, matches[matches.length - 1])
  }
  return null
}

const srcXpi = findSignedXpi()
if (!srcXpi) {
  console.error('[thunderbird-addin] No signed .xpi in dist/. Run npm run sign first (or copy a signed .xpi there).')
  process.exit(1)
}

const manifestUpdateUrl = manifest.applications?.gecko?.update_url
const expectedUpdateUrl = updatesJsonPublicUrl()
if (manifestUpdateUrl !== expectedUpdateUrl) {
  console.warn(
    `[thunderbird-addin] manifest applications.gecko.update_url is ${JSON.stringify(manifestUpdateUrl)}; expected ${JSON.stringify(expectedUpdateUrl)}.`,
  )
  console.warn('[thunderbird-addin] Re-sign after fixing manifest.json so auto-update uses this host.')
}

fs.mkdirSync(hostingDir, { recursive: true })

const xpiBasename = path.basename(srcXpi)
const destXpi = path.join(hostingDir, xpiBasename)
fs.copyFileSync(srcXpi, destXpi)

const updates = buildUpdatesManifest(version, xpiBasename)
fs.writeFileSync(path.join(hostingDir, 'updates.json'), `${JSON.stringify(updates, null, 2)}\n`, 'utf8')

const htaccessSrc = path.join(hostingDir, '.htaccess')
if (!fs.existsSync(htaccessSrc)) {
  console.warn('[thunderbird-addin] .htaccess missing in hosting/ — copy from repo template')
}

console.log('[thunderbird-addin] hosting bundle ready (upload entire folder to your web server):')
console.log(`  ${hostingDir}/`)
console.log(`    ${xpiBasename}`)
console.log('    updates.json')
console.log('    .htaccess')
console.log('    README.md')
console.log('')
console.log(`Add-on ID:     ${ADDON_ID}`)
console.log(`Update URL:    ${expectedUpdateUrl}`)
console.log(`XPI URL:       ${UPDATE_BASE_URL}/${xpiBasename}`)
console.log('')
console.log('WordPress: upload to public_html/thunderbird/ — see hosting/README.md')
