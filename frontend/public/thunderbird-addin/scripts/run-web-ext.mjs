import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const addinRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), '..')

export function runWebExt(args) {
  const localBin =
    process.platform === 'win32'
      ? path.join(addinRoot, 'node_modules', '.bin', 'web-ext.cmd')
      : path.join(addinRoot, 'node_modules', '.bin', 'web-ext')
  const cmd = fs.existsSync(localBin) ? localBin : 'web-ext'
  const result = spawnSync(cmd, args, { cwd: addinRoot, stdio: 'inherit', env: process.env })
  if (result.error) {
    console.error(result.error.message)
    process.exit(1)
  }
  if (result.status !== 0) process.exit(result.status ?? 1)
}

export { addinRoot }
