// CMS hosting adapter only. Source and canonical renderer belong to canary-outlook.
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import {fileURLToPath,pathToFileURL} from 'node:url'
const frontend=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
const digest=bytes=>crypto.createHash('sha256').update(bytes).digest('hex')
export async function loadPinnedBundle(vendor=path.join(frontend,'vendor/canary-outlook')) {
  const lock=JSON.parse(fs.readFileSync(path.join(vendor,'lock.json'),'utf8'))
  if(lock.schema!==1 || lock.source_dirty!==false || !/^[a-f0-9]{40}$/.test(lock.source_commit)) throw new Error('Outlook bundle requires a clean pinned source commit')
  for(const [name,key] of [['bundle.json','bundle_sha256'],['hosting.mjs','hosting_sha256']]) {
    if(digest(fs.readFileSync(path.join(vendor,name)))!==lock[key]) throw new Error('Outlook pin mismatch: '+name)
  }
  const api=await import(pathToFileURL(path.join(vendor,'hosting.mjs')).href)
  const bundle=path.join(vendor,'bundle.json');api.readBundle(bundle)
  return {api,bundle,lock}
}
function publicUrl() {
  if((process.env.CANARY_PUBLIC_URL||'').trim()) return process.env.CANARY_PUBLIC_URL
  const env=path.join(frontend,'../.env');if(!fs.existsSync(env))return ''
  const line=fs.readFileSync(env,'utf8').split('\n').find(x=>x.startsWith('CANARY_PUBLIC_URL='));if(!line)return ''
  let value=line.slice('CANARY_PUBLIC_URL='.length).trim()
  if((value.startsWith('"')&&value.endsWith('"'))||(value.startsWith("'")&&value.endsWith("'")))value=value.slice(1,-1)
  return value
}
export async function hostBundle(mode) {
  if(!['stage','dev','dist'].includes(mode))throw new Error('Expected stage, dev or dist')
  const {api,bundle,lock}=await loadPinnedBundle()
  const output=path.join(frontend,mode==='dist'?'dist':'public')
  if(mode==='dist'&&!fs.existsSync(output))throw new Error('Build frontend before rendering Outlook output')
  // Icons are shared with CMS. Coordinate source changes instead of silently changing CMS branding.
  for(const [name,record] of Object.entries(api.readBundle(bundle).files).filter(([n])=>n.startsWith('icons/'))){
    const existing=path.join(frontend,'public',name)
    if(fs.existsSync(existing)&&digest(fs.readFileSync(existing))!==record.sha256)throw new Error('Shared Outlook/CMS icon differs: '+name)
  }
  const origin=mode==='stage'?'':api.normalizeOrigin(publicUrl())
  api.stageBundle(bundle,output,origin)
  console.log('[outlook-addin] verified pinned bundle',lock.source_commit,api.verifyOutput(bundle,output,origin),'files')
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))await hostBundle(process.argv[2]||'stage')
