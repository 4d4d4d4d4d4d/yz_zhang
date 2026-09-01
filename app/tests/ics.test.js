import { describe, it, expect } from 'vitest'
import { buildEvent, escapeText, foldLine } from '../src/logic/ics.js'

describe('escapeText', () => {
  it('escapes backslash, semicolon, comma and newline', () => {
    expect(escapeText('a\\b;c,d\ne')).toBe('a\\\\b\\;c\\,d\\ne')
  })
  it('renders nullish as empty', () => {
    expect(escapeText(undefined)).toBe('')
  })
})

describe('foldLine', () => {
  it('leaves short lines untouched', () => {
    expect(foldLine('SUMMARY:hi')).toBe('SUMMARY:hi')
  })
  it('folds a long line with leading-space continuations', () => {
    const long = 'DESCRIPTION:' + 'x'.repeat(200)
    const folded = foldLine(long)
    const parts = folded.split('\r\n')
    expect(parts.length).toBeGreaterThan(1)
    expect(parts[0].length).toBe(75)
    expect(parts.slice(1).every(p => p.startsWith(' '))).toBe(true)
    // unfolding restores the original
    expect(parts.map((p, i) => i ? p.slice(1) : p).join('')).toBe(long)
  })
})

describe('buildEvent', () => {
  const ev = buildEvent({
    title: 'Shanghai ↔ Tokyo',
    start: Date.UTC(2026, 6, 27, 1, 0, 0),
    end: Date.UTC(2026, 6, 27, 2, 0, 0),
    description: 'Cross-border sync',
    location: 'Immersive meeting',
    uid: 'u-1',
    now: Date.UTC(2026, 6, 20, 0, 0, 0)
  })

  it('includes DESCRIPTION and LOCATION when provided', () => {
    expect(ev).toContain('DESCRIPTION:Cross-border sync')
    expect(ev).toContain('LOCATION:Immersive meeting')
  })

  it('wraps a single VEVENT in a VCALENDAR', () => {
    expect(ev).toMatch(/^BEGIN:VCALENDAR/)
    expect(ev.trimEnd()).toMatch(/END:VCALENDAR$/)
    expect(ev).toContain('BEGIN:VEVENT')
    expect(ev).toContain('END:VEVENT')
  })

  it('formats DTSTART/DTEND/DTSTAMP as UTC', () => {
    expect(ev).toContain('DTSTART:20260727T010000Z')
    expect(ev).toContain('DTEND:20260727T020000Z')
    expect(ev).toContain('DTSTAMP:20260720T000000Z')
    expect(ev).toContain('UID:u-1')
  })

  it('uses CRLF line endings', () => {
    expect(ev).toContain('\r\n')
    expect(ev).not.toMatch(/[^\r]\n/)
  })

  it('omits DESCRIPTION/LOCATION when empty', () => {
    const bare = buildEvent({ title: 'x', start: 0, end: 1000 })
    expect(bare).not.toContain('DESCRIPTION:')
    expect(bare).not.toContain('LOCATION:')
  })

  it('escapes text fields', () => {
    const e = buildEvent({ title: 'A, B; C', start: 0, end: 1 })
    expect(e).toContain('SUMMARY:A\\, B\\; C')
  })
})
