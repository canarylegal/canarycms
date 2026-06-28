import fs from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const addinRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), '..')
const hostingDir = path.join(addinRoot, 'hosting')

const smbHost = process.env.SMB_HOST || 'truenas.local'
const smbShare = process.env.SMB_SHARE || 'thunderbird'
const smbUser = process.env.SMB_USER || 'cmcwilli'
const smbPassword = process.env.SMB_PASSWORD || ''

const files = ['updates.json', '.htaccess']
const xpis = fs.existsSync(hostingDir)
  ? fs.readdirSync(hostingDir).filter((name) => name.endsWith('.xpi'))
  : []

if (xpis.length === 0) {
  console.error('[thunderbird-addin] No .xpi in hosting/. Run: npm run release')
  process.exit(1)
}

for (const name of [...files, ...xpis]) {
  const local = path.join(hostingDir, name)
  if (!fs.existsSync(local)) {
    console.error(`[thunderbird-addin] Missing ${local}`)
    process.exit(1)
  }
}

if (!smbPassword) {
  console.error('[thunderbird-addin] Set SMB_PASSWORD for //' + smbHost + '/' + smbShare)
  console.error('Example: SMB_PASSWORD=\'…\' npm run deploy-smb')
  process.exit(1)
}

function smbPut(localPath, remoteName) {
  const cmd = `put ${JSON.stringify(localPath)} ${JSON.stringify(remoteName)}`
  const result = spawnSync(
    'smbclient',
    [`//${smbHost}/${smbShare}`, `-U`, `${smbUser}%${smbPassword}`, '-c', cmd],
    { stdio: 'inherit' },
  )
  if (result.status !== 0) process.exit(result.status ?? 1)
}

for (const name of [...files, ...xpis]) {
  console.log(`[thunderbird-addin] uploading ${name}…`)
  smbPut(path.join(hostingDir, name), name)
}

console.log('[thunderbird-addin] uploaded to smb://' + smbUser + '@' + smbHost + '/' + smbShare + '/')
