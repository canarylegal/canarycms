/**
 * Copy repo-root thunderbird-addin into public/, then verify Vite dist output after build.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.join(__dirname, '..')
const repoRoot = path.join(frontendRoot, '..')
const src = path.join(repoRoot, 'thunderbird-addin')
const destPublic = path.join(frontendRoot, 'public', 'thunderbird-addin')

const REQUIRED = [
  'manifest.json',
  'background.js',
  'canary-windows.js',
  'canary-shared.js',
  'compose-store.js',
  'compose-prefill.js',
  'compose-apply.js',
  'canary-theme.css',
  'compose-send.js',
  'compose-auto-open.js',
  'compose-attach-ui.js',
  'filing-menu.js',
  'tag-apply.js',
  'compose-panel/panel.html',
  'compose-panel/panel.js',
  'compose-panel/panel.css',
  'compose-panel/attach-picker.html',
  'compose-panel/attach-picker.js',
  'popup/popup.html',
  'popup/popup.js',
  'popup/popup.css',
  'icons/icon16.png',
  'icons/icon32.png',
  'icons/icon64.png',
  'icons/icon128.png',
]

const SYNC_SKIP_NAMES = new Set([
  'package.json',
  'package-lock.json',
  'node_modules',
  'dist',
  'web-ext-artifacts',
  '.amo-upload-uuid',
  'scripts',
])

function copyRecursive(srcDir, destDir) {
  fs.mkdirSync(destDir, { recursive: true })
  for (const name of fs.readdirSync(srcDir)) {
    if (name.endsWith('.nextcloud') || SYNC_SKIP_NAMES.has(name)) continue
    const s = path.join(srcDir, name)
    const d = path.join(destDir, name)
    const st = fs.statSync(s)
    if (st.isDirectory()) {
      copyRecursive(s, d)
    } else {
      fs.copyFileSync(s, d)
    }
  }
}

if (!fs.existsSync(src)) {
  if (fs.existsSync(path.join(destPublic, 'manifest.json'))) {
    console.log(
      '[thunderbird-addin] repo source missing; using existing public/thunderbird-addin/ (Docker build context)',
    )
  } else {
    console.error('[thunderbird-addin] missing source:', src)
    process.exit(1)
  }
} else {
  copyRecursive(src, destPublic)
  console.log('[thunderbird-addin] synced to public/thunderbird-addin/')
}

const distAddin = path.join(frontendRoot, 'dist', 'thunderbird-addin')
if (!fs.existsSync(path.join(frontendRoot, 'dist'))) {
  console.log('[thunderbird-addin] skip dist verify (no dist/ yet)')
  process.exit(0)
}

let ok = true
for (const f of REQUIRED) {
  const p = path.join(distAddin, f)
  if (!fs.existsSync(p)) {
    console.error('[thunderbird-addin] missing build output:', p)
    ok = false
  }
}
if (!ok) process.exit(1)
console.log('[thunderbird-addin] verified:', REQUIRED.length, 'files in dist/thunderbird-addin/')
