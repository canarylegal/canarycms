import {test} from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import {fileURLToPath} from 'node:url'
import crypto from 'node:crypto'
import {loadPinnedBundle} from '../outlook-bundle.mjs'
const vendor=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../vendor/canary-outlook')
function copy(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'cms-outlook-'));fs.cpSync(vendor,dir,{recursive:true});t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return dir}
test('clean pinned Outlook bundle loads and produces required hosted files',async t=>{const dir=copy(t);const {api,bundle}=await loadPinnedBundle(dir);const site=path.join(dir,'site');api.stageBundle(bundle,site,'https://canary.example.org');assert.equal(api.verifyOutput(bundle,site,'https://canary.example.org'),25);assert(fs.existsSync(path.join(site,'outlook-addin/commands-launch.js')));assert(fs.existsSync(path.join(site,'.well-known/microsoft-officeaddins-allowed.json')))})
for(const name of ['bundle.json','hosting.mjs'])test('reject modified pinned '+name,async t=>{const dir=copy(t);fs.appendFileSync(path.join(dir,name),' ');await assert.rejects(loadPinnedBundle(dir),/pin mismatch/)})
test('reject uncommitted source bundle',async t=>{const dir=copy(t);const file=path.join(dir,'lock.json'),lock=JSON.parse(fs.readFileSync(file));lock.source_dirty=true;fs.writeFileSync(file,JSON.stringify(lock));await assert.rejects(loadPinnedBundle(dir),/clean pinned/)})
test('reject traversal even if outer digest was updated',async t=>{const dir=copy(t),file=path.join(dir,'bundle.json'),b=JSON.parse(fs.readFileSync(file));b.files['outlook-addin/../escape.js']=b.files['outlook-addin/taskpane.js'];fs.writeFileSync(file,JSON.stringify(b));const lock=JSON.parse(fs.readFileSync(path.join(dir,'lock.json')));lock.bundle_sha256=crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');fs.writeFileSync(path.join(dir,'lock.json'),JSON.stringify(lock));await assert.rejects(loadPinnedBundle(dir),/Unsafe Outlook path/)})
