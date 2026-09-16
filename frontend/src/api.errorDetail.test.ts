import { describe, expect, it } from 'vitest'
import { formatApiErrorDetail } from './api'

describe('formatApiErrorDetail', () => {
  it('returns fallback for null/empty bodies', () => {
    expect(formatApiErrorDetail(null, 'HTTP 500')).toBe('HTTP 500')
    expect(formatApiErrorDetail('   ', 'HTTP 500')).toBe('HTTP 500')
    expect(formatApiErrorDetail({ other: true }, 'HTTP 400')).toBe('HTTP 400')
  })

  it('reads FastAPI string and validation-array detail', () => {
    expect(formatApiErrorDetail({ detail: 'Nope' }, 'fb')).toBe('Nope')
    expect(
      formatApiErrorDetail({ detail: [{ msg: 'field a' }, { msg: 'field b' }, 'plain'] }, 'fb'),
    ).toBe('field a field b plain')
  })

  it('humanizes lock objects and nested message detail', () => {
    expect(formatApiErrorDetail({ detail: { locked_by: 'Ada' } }, 'fb')).toBe(
      'This file is already being edited by Ada.',
    )
    expect(formatApiErrorDetail({ detail: { message: 'Busy' } }, 'fb')).toBe('Busy')
  })

  it('humanizes Cloudflare HTML error pages', () => {
    const html = '<!DOCTYPE html><html><head><title>502 Bad Gateway | Cloudflare</title></head><body>cloudflare</body></html>'
    const msg = formatApiErrorDetail(html, 'HTTP 502', 'https://app.example/api/x')
    expect(msg).toContain('Cloudflare')
    expect(msg).toContain('Request: https://app.example/api/x')
    expect(msg).toContain('HTTP 502')
    expect(msg).not.toContain('<!DOCTYPE')
  })

  it('humanizes nginx HTML error pages with title', () => {
    const html = '<html><head><title>502 Bad Gateway</title></head><body>nginx</body></html>'
    const msg = formatApiErrorDetail(html, 'HTTP 502')
    expect(msg).toContain('reverse proxy')
    expect(msg).toContain('502 Bad Gateway')
  })

  it('snips very long non-HTML plain text', () => {
    const long = 'x'.repeat(2500)
    const msg = formatApiErrorDetail(long, 'fb')
    expect(msg.endsWith('…')).toBe(true)
    expect(msg.length).toBeLessThan(long.length)
  })
})
