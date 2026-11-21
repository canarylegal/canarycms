// Canonical offline hosting adapter. Vendored into CMS as a checksum-pinned build dependency.
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
export const TEMPLATE_ORIGIN = 'https://YOUR_CANARY_PUBLIC_URL'
export const sha256 = data => crypto.createHash('sha256').update(data).digest('hex')
export function normalizeOrigin(raw) {
  const s = (raw || '').trim().replace(/\/$/, '')
  if (!s) return ''
  try { return new URL(s.includes('://') ? s : `https://${s}`).origin } catch { return '' }
}
export function rewriteManifestXml(xml, origin) {
  if (!origin) return xml
  const from = [TEMPLATE_ORIGIN, 'https://testing.canarylegalsoftware.co.uk', 'https://dev.canarylegalsoftware.co.uk'].filter(x => x !== origin)
  return xml.split(/(<!--[\s\S]*?-->)/g).map(part => part.startsWith('<!--') ? part : from.reduce((s,x) => s.split(x).join(origin),part)).join('')
}
export function readBundle(file) {
  const bundle = JSON.parse(fs.readFileSync(file, 'utf8'))
  if (bundle.schema !== 1 || !bundle.files || Array.isArray(bundle.files)) throw new Error('Invalid Outlook bundle')
  for (const [name, record] of Object.entries(bundle.files)) {
    if (!/^(outlook-addin\/[A-Za-z0-9.-]+|icons\/icon(16|32|64|80|128)\.png|\.well-known\/microsoft-officeaddins-allowed\.json)$/.test(name) || name.includes('..')) throw new Error('Unsafe Outlook path: '+name)
    if (typeof record.content !== 'string' || sha256(Buffer.from(record.content,'base64')) !== record.sha256) throw new Error('Invalid Outlook content: '+name)
  }
  for (const name of ['outlook-addin/manifest.xml','outlook-addin/taskpane.html','outlook-addin/auth-callback.html','.well-known/microsoft-officeaddins-allowed.json']) if (!bundle.files[name]) throw new Error('Missing Outlook entry: '+name)
  return bundle
}
export function stageBundle(file, output, origin = '') {
  const bundle = readBundle(file)
  fs.rmSync(path.join(output,'outlook-addin'),{recursive:true,force:true})
  for (const [name, record] of Object.entries(bundle.files)) {
    let data = Buffer.from(record.content,'base64')
    if (name==='outlook-addin/manifest.xml' || name==='.well-known/microsoft-officeaddins-allowed.json') data=Buffer.from(rewriteManifestXml(data.toString(),origin))
    const target=path.join(output,name);fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,data)
  }
  return bundle
}
export function verifyOutput(file, output, origin = '') {
  const bundle=readBundle(file)
  for (const [name,record] of Object.entries(bundle.files)) {
    let expected=Buffer.from(record.content,'base64')
    if (name==='outlook-addin/manifest.xml' || name==='.well-known/microsoft-officeaddins-allowed.json') expected=Buffer.from(rewriteManifestXml(expected.toString(),origin))
    if (!fs.readFileSync(path.join(output,name)).equals(expected)) throw new Error('Outlook output differs: '+name)
  }
  return Object.keys(bundle.files).length
}
