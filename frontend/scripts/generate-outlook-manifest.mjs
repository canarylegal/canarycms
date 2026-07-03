/**
 * Rewrite ``dist/outlook-addin/manifest.xml`` URLs to match ``CANARY_PUBLIC_URL`` at build time.
 *
 * Committed ``public/outlook-addin/manifest.xml`` uses placeholder https://YOUR_CANARY_PUBLIC_URL.
 * Docker / CI sets CANARY_PUBLIC_URL; locally, the script reads repo ``.env``.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.join(__dirname, '..')
const repoRoot = path.join(frontendRoot, '..')

/** Placeholder origin in committed ``public/outlook-addin/manifest.xml``. */
export const TEMPLATE_ORIGIN = 'https://YOUR_CANARY_PUBLIC_URL'

/** Older committed origins — still rewritten if present in a checkout. */
const LEGACY_ORIGINS = [
  'https://testing.canarylegalsoftware.co.uk',
  'https://dev.canarylegalsoftware.co.uk',
]

function readEnvFileValue(key) {
  const envPath = path.join(repoRoot, '.env')
  if (!fs.existsSync(envPath)) return ''
  const line = fs
    .readFileSync(envPath, 'utf8')
    .split('\n')
    .find((l) => l.startsWith(`${key}=`))
  if (!line) return ''
  const raw = line.slice(key.length + 1).trim()
  if ((raw.startsWith('"') && raw.endsWith('"')) || (raw.startsWith("'") && raw.endsWith("'"))) {
    return raw.slice(1, -1)
  }
  return raw
}

export function resolvePublicOrigin() {
  const fromEnv = (process.env.CANARY_PUBLIC_URL || '').trim()
  if (fromEnv) return normalizeOrigin(fromEnv)
  return normalizeOrigin(readEnvFileValue('CANARY_PUBLIC_URL'))
}

export function normalizeOrigin(raw) {
  const s = (raw || '').trim().replace(/\/$/, '')
  if (!s) return ''
  try {
    const u = new URL(s.includes('://') ? s : `https://${s}`)
    return u.origin
  } catch {
    console.warn('[outlook-addin] invalid CANARY_PUBLIC_URL — keeping manifest origin')
    return ''
  }
}

export function rewriteManifestXml(xml, origin) {
  if (!origin) return xml
  let out = xml
  for (const from of [TEMPLATE_ORIGIN, ...LEGACY_ORIGINS]) {
    if (from !== origin && out.includes(from)) {
      out = out.split(from).join(origin)
    }
  }
  return out
}

function parseArgs(argv) {
  let target = 'dist'
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--target' && argv[i + 1]) {
      target = argv[++i]
    }
  }
  return { target }
}

const { target } = parseArgs(process.argv.slice(2))
const origin = resolvePublicOrigin()

const baseDir =
  target === 'public'
    ? path.join(frontendRoot, 'public', 'outlook-addin')
    : path.join(frontendRoot, 'dist', 'outlook-addin')

if (!fs.existsSync(baseDir)) {
  console.log(`[outlook-addin] skip ${target} rewrite (no ${baseDir})`)
  process.exit(0)
}

const manifestPath = path.join(baseDir, 'manifest.xml')
const sendManifestPath = path.join(baseDir, 'manifest-with-send.xml')
const minimalManifestPath = path.join(baseDir, 'manifest-minimal.xml')
if (!fs.existsSync(manifestPath)) {
  console.error('[outlook-addin] missing', manifestPath)
  process.exit(1)
}

if (!origin) {
  console.warn(
    `[outlook-addin] CANARY_PUBLIC_URL is not set — ${target}/manifest.xml keeps committed URLs (${TEMPLATE_ORIGIN}).`,
  )
  process.exit(0)
}

function rewriteManifestAt(pathToManifest) {
  if (!fs.existsSync(pathToManifest)) return
  const before = fs.readFileSync(pathToManifest, 'utf8')
  const after = rewriteManifestXml(before, origin)
  if (after === before) {
    console.log(`[outlook-addin] ${path.relative(frontendRoot, pathToManifest)} already uses ${origin}`)
  } else {
    fs.writeFileSync(pathToManifest, after)
    console.log(`[outlook-addin] ${path.relative(frontendRoot, pathToManifest)} URLs → ${origin}`)
  }
}

rewriteManifestAt(manifestPath)
rewriteManifestAt(sendManifestPath)
rewriteManifestAt(minimalManifestPath)

if (!origin.startsWith('https://') && !/^https:\/\/localhost(:\d+)?$/i.test(origin)) {
  console.warn(
    `[outlook-addin] warning: ${origin} is not HTTPS — Outlook may reject the add-in except on localhost`,
  )
}
