import { describe, it, expect } from 'vitest'
import { validateContact, EMAIL_RE } from '../src/logic/validation.js'
import { event, createRecorder, EVENTS } from '../src/logic/analytics.js'

const GOOD = { name: 'Mei', email: 'mei@lumi.co.jp', company: 'Lumi', message: 'Launching in JP', region: '', role: 'brand' }

describe('validateContact', () => {
  it('accepts a fully valid form', () => {
    expect(validateContact(GOOD)).toEqual({ valid: true, errors: {} })
  })

  it('flags each missing required field with the required key', () => {
    for (const field of ['name', 'email', 'company', 'message']) {
      const { valid, errors } = validateContact({ ...GOOD, [field]: '  ' })
      expect(valid).toBe(false)
      expect(errors[field]).toBe(field === 'email' ? 'contact.err.required' : 'contact.err.required')
    }
  })

  it('rejects malformed emails with the email key; accepts real-world ones', () => {
    for (const bad of ['x', 'a@b', 'a b@c.com', 'a@b.c']) {
      expect(validateContact({ ...GOOD, email: bad }).errors.email, bad).toBe('contact.err.email')
    }
    for (const good of ['a@b.co', 'first.last+tag@sub.domain.io', '用户@例子.中国']) {
      expect(validateContact({ ...GOOD, email: good }).valid, good).toBe(true)
    }
  })

  it('region and role are optional; empty form reports all four required fields', () => {
    expect(validateContact({ ...GOOD, region: '', role: '' }).valid).toBe(true)
    const { errors } = validateContact({})
    expect(Object.keys(errors).sort()).toEqual(['company', 'email', 'message', 'name'])
  })

  it('EMAIL_RE requires a dotted TLD of 2+ chars', () => {
    expect(EMAIL_RE.test('a@b.co')).toBe(true)
    expect(EMAIL_RE.test('a@b.c')).toBe(false)
  })
})

describe('analytics', () => {
  it('event normalizes name/props/timestamp and rejects unknown names', () => {
    const e = event('form_submit', { form: 'contact' }, 1000)
    expect(e).toEqual({ name: 'form_submit', props: { form: 'contact' }, at: 1000 })
    expect(() => event('form_submitt')).toThrow(/unknown analytics event/)
  })

  it('every funnel stage is in the allowlist', () => {
    for (const n of ['form_view', 'form_submit', 'form_error', 'form_success']) {
      expect(EVENTS).toContain(n)
    }
  })

  it('recorder keeps a ring buffer and counts by name', () => {
    const r = createRecorder({ limit: 3 })
    r.record('page_view', {}, 1)
    r.record('form_view', {}, 2)
    r.record('form_submit', {}, 3)
    r.record('form_success', {}, 4) // evicts page_view
    expect(r.all()).toHaveLength(3)
    expect(r.all()[0].name).toBe('form_view')
    expect(r.countByName('page_view')).toBe(0)
    expect(r.countByName('form_submit')).toBe(1)
  })

  it('a full funnel is countable: view → submit → error → submit → success', () => {
    const r = createRecorder()
    r.record('form_view'); r.record('form_submit'); r.record('form_error')
    r.record('form_submit'); r.record('form_success')
    expect(r.countByName('form_submit')).toBe(2)
    expect(r.countByName('form_error')).toBe(1)
    expect(r.countByName('form_success')).toBe(1)
    r.clear()
    expect(r.all()).toEqual([])
  })
})
