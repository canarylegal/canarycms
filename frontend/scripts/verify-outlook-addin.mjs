/**
 * Ensures the Outlook add-in shipped under public/outlook-addin is present in the Vite dist output.
 * Run automatically after `npm run build` via postbuild.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.join(__dirname, '..')

const REQUIRED_DIST = [
  'manifest.xml',
  'icons/icon16.png',
  'icons/icon32.png',
  'icons/icon64.png',
  'icons/icon80.png',
  'icons/icon128.png',
  'taskpane.html',
  'taskpane.js',
  'compose-pane.html',
  'compose-pane.js',
  'compose-apply.js',
  'attach-picker.html',
  'attach-picker.js',
  'attach-picker.css',
  'outlook-compose-attach-ui.js',
  'outlook-shared.js',
  'commands.html',
  'commands.js',
  'auth-callback.html',
  'auth-callback.js',
  'styles.css',
]

/** PNG dimensions Outlook expects for mail add-in icons (exact match required). */
const ICON_SIZES = {
  'icons/icon16.png': 16,
  'icons/icon32.png': 32,
  'icons/icon64.png': 64,
  'icons/icon80.png': 80,
  'icons/icon128.png': 128,
  'outlook-addin/icons/icon16.png': 16,
  'outlook-addin/icons/icon32.png': 32,
  'outlook-addin/icons/icon64.png': 64,
  'outlook-addin/icons/icon80.png': 80,
  'outlook-addin/icons/icon128.png': 128,
}

function readPngDimensions(filePath) {
  const buf = fs.readFileSync(filePath)
  if (buf.length < 24 || buf[0] !== 0x89 || buf.toString('ascii', 1, 4) !== 'PNG') {
    return null
  }
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) }
}

const distAddin = path.join(root, 'dist', 'outlook-addin')

if (!fs.existsSync(path.join(root, 'dist'))) {
  console.error('[outlook-addin] dist/ missing — run npm run build first')
  process.exit(1)
}

let ok = true
for (const f of REQUIRED_DIST) {
  const p = path.join(distAddin, f)
  if (!fs.existsSync(p)) {
    console.error('[outlook-addin] missing build output:', p)
    ok = false
  }
}

for (const [rel, size] of Object.entries(ICON_SIZES)) {
  const p = path.join(root, 'public', rel)
  if (!fs.existsSync(p)) {
    console.error('[outlook-addin] missing icon:', p)
    ok = false
    continue
  }
  const dim = readPngDimensions(p)
  if (!dim || dim.width !== size || dim.height !== size) {
    console.error(
      `[outlook-addin] ${rel} must be ${size}x${size}px (got ${dim ? `${dim.width}x${dim.height}` : 'invalid PNG'})`,
    )
    ok = false
  }
}

if (!ok) process.exit(1)
console.log('[outlook-addin] verified:', REQUIRED_DIST.length, 'files in dist/outlook-addin/')
