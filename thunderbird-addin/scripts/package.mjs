import fs from 'node:fs'
import path from 'node:path'
import { addinRoot, runWebExt } from './run-web-ext.mjs'

const manifest = JSON.parse(fs.readFileSync(path.join(addinRoot, 'manifest.json'), 'utf8'))
const version = manifest.version
const filename = `canary-thunderbird-${version}.zip`
const distDir = process.env.CANARY_TB_ARTIFACTS_DIR || path.join(addinRoot, '.build-out')

fs.mkdirSync(distDir, { recursive: true })

runWebExt([
  'build',
  '--source-dir',
  addinRoot,
  '--artifacts-dir',
  distDir,
  '--overwrite-dest',
  '--filename',
  filename,
])

console.log(`[thunderbird-addin] packaged ${path.relative(addinRoot, path.join(distDir, filename))}`)
console.log('[thunderbird-addin] install the signed copy after npm run sign, or submit this zip to ATN manually')
