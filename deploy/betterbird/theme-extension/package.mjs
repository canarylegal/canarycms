#!/usr/bin/env node
/** Build canary-theme.xpi for Betterbird (Settings → Add-ons → Install from file). */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'url'
import { execFileSync } from 'node:child_process'

const root = path.dirname(fileURLToPath(import.meta.url))
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json'), 'utf8'))
const version = manifest.version
const outDir = path.join(root, 'dist')
const xpiName = `canary-theme-${version}.xpi`
const xpiPath = path.join(outDir, xpiName)

const files = ['manifest.json', 'canary-extras.css', 'canary-logo-datauri.css', 'canary-logo.jpg'].filter(
  (f) => fs.existsSync(path.join(root, f)),
)

fs.mkdirSync(outDir, { recursive: true })

const zipArgs = ['-j', xpiPath, ...files]
try {
  execFileSync('zip', zipArgs, { cwd: root, stdio: 'inherit' })
} catch {
  execFileSync(
    'python3',
    [
      '-c',
      `
import zipfile, sys, os
root = sys.argv[1]
out = sys.argv[2]
files = sys.argv[3:]
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in files:
        z.write(os.path.join(root, f), f)
`,
      root,
      xpiPath,
      ...files,
    ],
    { stdio: 'inherit' },
  )
}
console.log(`Built ${xpiPath}`)
