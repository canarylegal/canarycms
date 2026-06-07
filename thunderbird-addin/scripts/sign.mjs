import fs from 'node:fs'
import path from 'node:path'
import { addinRoot, runWebExt } from './run-web-ext.mjs'

const apiKey = process.env.ATN_API_KEY || process.env.WEB_EXT_API_KEY
const apiSecret = process.env.ATN_API_SECRET || process.env.WEB_EXT_API_SECRET

if (!apiKey || !apiSecret) {
  console.error('[thunderbird-addin] Missing ATN API credentials.')
  console.error('Set ATN_API_KEY and ATN_API_SECRET (from https://addons.thunderbird.net/developers/addon/api/key/).')
  console.error('See thunderbird-addin/README.md § "Sign a release (maintainers)".')
  process.exit(1)
}

const amoBaseUrl = process.env.ATN_AMO_BASE_URL || 'https://addons.thunderbird.net/api/v4'
const distDir = path.join(addinRoot, 'dist')
fs.mkdirSync(distDir, { recursive: true })

const args = [
  'sign',
  '--source-dir',
  addinRoot,
  '--artifacts-dir',
  distDir,
  '--channel',
  'unlisted',
  '--amo-base-url',
  amoBaseUrl,
  '--api-key',
  apiKey,
  '--api-secret',
  apiSecret,
  '--overwrite-dest',
  '--approval-timeout',
  '900000',
]

const metadataPath = path.join(addinRoot, 'scripts', 'amo-metadata.json')
if (fs.existsSync(metadataPath)) {
  args.push('--amo-metadata', metadataPath)
}

runWebExt(args)

const artifacts = fs.readdirSync(distDir).filter((name) => name.endsWith('.xpi') || name.endsWith('.zip'))
if (artifacts.length === 0) {
  console.error('[thunderbird-addin] sign finished but no .xpi found in dist/')
  process.exit(1)
}

console.log('[thunderbird-addin] signed add-on(s) in dist/:')
for (const name of artifacts) console.log(`  - ${name}`)
