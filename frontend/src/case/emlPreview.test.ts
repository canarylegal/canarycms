import { describe, expect, it } from 'vitest'
import { sanitizeEmlHtml, wrapEmailHtmlDocument } from './emlPreview'

describe('eml HTML sanitization', () => {
  it('strips remote images and CSS urls when remote content is disallowed', () => {
    const html = `
      <p>Hello</p>
      <img src="https://tracker.example/pixel.gif" alt="x" />
      <img src="data:image/gif;base64,AAAA" alt="ok" />
      <div style="background-image: url(https://evil.example/bg.png)">styled</div>
      <style>.x { background: url("https://evil.example/a.png"); }</style>
    `
    const out = sanitizeEmlHtml(html, false)
    expect(out).toContain('Hello')
    expect(out).not.toContain('https://tracker.example/pixel.gif')
    expect(out).toContain('data:image/gif;base64,AAAA')
    expect(out).not.toContain('https://evil.example/bg.png')
    expect(out).not.toContain('https://evil.example/a.png')
  })

  it('keeps remote images when allowRemote is true', () => {
    const out = sanitizeEmlHtml('<img src="https://cdn.example/a.png" alt="x" />', true)
    expect(out).toContain('https://cdn.example/a.png')
  })

  it('embeds a restrictive CSP in the iframe document when remote is blocked', () => {
    const doc = wrapEmailHtmlDocument('<p>hi</p>', false)
    expect(doc).toContain('Content-Security-Policy')
    expect(doc).toContain("img-src data: blob: cid:")
    expect(doc).not.toMatch(/img-src[^;]*https:/)
  })

  it('allows https images in CSP when remote is allowed', () => {
    const doc = wrapEmailHtmlDocument('<p>hi</p>', true)
    expect(doc).toMatch(/img-src[^;]*https:/)
  })
})
