import { describe, expect, it } from 'vitest'
import { parseEmlForPreview, sanitizeEmlHtml, wrapEmailHtmlDocument } from './emlPreview'

describe('parseEmlForPreview multipart', () => {
  it('does not dump base64 attachment payloads as the body', () => {
    const wavB64 = 'UklGRqb0AwBXQVZFZm10IBIAAAABAAEAQB8AAIA+AAACABAAAABkYXRh' + 'AAgA'.repeat(80)
    const raw = [
      'From: noreply@3cx.net',
      'To: colin@example.com',
      'Subject: New Voicemail',
      'Date: Thu, 01 Oct 2026 09:52:38 +0000',
      'MIME-Version: 1.0',
      'Content-Type: multipart/mixed; boundary="aa953bdd2aed"',
      '',
      'Business communications. AI-powered. Your way.',
      '--aa953bdd2aed',
      'Content-Type: text/plain; charset=utf-8',
      '',
      'You have a new voicemail.',
      '--aa953bdd2aed',
      'Content-Disposition: attachment; filename="vmail.wav"',
      'Content-Transfer-Encoding: base64',
      'Content-Type: application/octet-stream; name="vmail.wav"',
      '',
      wavB64,
      '--aa953bdd2aed--',
      '',
    ].join('\r\n')
    const parsed = parseEmlForPreview(raw)
    expect(parsed.subject).toBe('New Voicemail')
    expect(parsed.bodyText).toContain('You have a new voicemail.')
    expect(parsed.bodyText).not.toContain('Content-Transfer-Encoding')
    expect(parsed.bodyText).not.toContain(wavB64.slice(0, 40))
  })

  it('renders HTML from multipart/alternative with ----=_Part_ boundaries', () => {
    const boundary = '----=_Part_737278_1561730413.1790758446657'
    const raw = [
      'From: "Ewan Sturman" <bni.notifications@bniconnectglobal.com>',
      'To: staff@example.com',
      'Subject: October events',
      'Date: Wed, 30 Sep 2026 08:54:29 +0000',
      `Content-Type: multipart/alternative; boundary="${boundary}"`,
      '',
      `--${boundary}`,
      'Content-Type: text/plain; charset=utf-8',
      'Content-Transfer-Encoding: 7bit',
      '',
      'Hi Everyone',
      '',
      `--${boundary}`,
      'Content-Type: text/html; charset=utf-8',
      'Content-Transfer-Encoding: 7bit',
      '',
      "<div style='font-family:Arial'><p>Hi Everyone</p><p>Leadership Training</p></div>",
      `--${boundary}--`,
      '',
    ].join('\r\n')
    const parsed = parseEmlForPreview(raw)
    expect(parsed.bodyHtml).toBeTruthy()
    expect(parsed.bodyHtml).toContain('Leadership Training')
    expect(parsed.bodyText).toContain('Hi Everyone')
    expect(parsed.bodyText).not.toContain('Content-Type: text/html')
    expect(parsed.bodyText).not.toContain(`--${boundary}`)
  })

  it('shows a friendly message for attachment-only multipart mail', () => {
    const wavB64 = ('AAgA'.repeat(100))
    const raw = [
      'From: noreply@3cx.net',
      'Subject: New Voicemail',
      'Content-Type: multipart/mixed; boundary="onlyatt"',
      '',
      '--onlyatt',
      'Content-Disposition: attachment; filename="vmail.wav"',
      'Content-Transfer-Encoding: base64',
      'Content-Type: application/octet-stream; name="vmail.wav"',
      '',
      wavB64,
      '--onlyatt--',
      '',
    ].join('\r\n')
    const parsed = parseEmlForPreview(raw)
    expect(parsed.bodyText).toMatch(/No readable message body/i)
    expect(parsed.bodyText).toContain('vmail.wav')
    expect(parsed.bodyText).not.toContain('Content-Transfer-Encoding')
  })
})

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
