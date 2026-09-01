import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SubTabs from '../src/components/SubTabs.vue'

const TABS = [
  { v: 'a', label: 'Alpha' },
  { v: 'b', label: 'Bravo' },
  { v: 'c', label: 'Charlie' }
]

function make(modelValue = 'a') {
  return mount(SubTabs, { props: { tabs: TABS, modelValue } })
}

describe('SubTabs — WAI-ARIA Tabs pattern', () => {
  it('is a tablist of tabs with exactly one aria-selected', () => {
    const w = make('b')
    expect(w.find('[role="tablist"]').exists()).toBe(true)
    const tabs = w.findAll('[role="tab"]')
    expect(tabs).toHaveLength(3)
    const selected = tabs.filter(t => t.attributes('aria-selected') === 'true')
    expect(selected).toHaveLength(1)
    expect(selected[0].text()).toContain('Bravo')
  })

  it('roving tabindex: selected tab is 0, the rest −1', () => {
    const tabs = make('b').findAll('[role="tab"]')
    expect(tabs.map(t => t.attributes('tabindex'))).toEqual(['-1', '0', '-1'])
  })

  it('ArrowRight moves selection and wraps at the end', async () => {
    const w = make('c') // last tab
    await w.findAll('[role="tab"]')[2].trigger('keydown', { key: 'ArrowRight' })
    expect(w.emitted('update:modelValue').at(-1)).toEqual(['a']) // wrapped to first
  })

  it('ArrowLeft moves back and wraps at the start', async () => {
    const w = make('a')
    await w.findAll('[role="tab"]')[0].trigger('keydown', { key: 'ArrowLeft' })
    expect(w.emitted('update:modelValue').at(-1)).toEqual(['c'])
  })

  it('Home and End jump to first and last', async () => {
    const w = make('b')
    await w.findAll('[role="tab"]')[1].trigger('keydown', { key: 'End' })
    expect(w.emitted('update:modelValue').at(-1)).toEqual(['c'])
    await w.findAll('[role="tab"]')[1].trigger('keydown', { key: 'Home' })
    expect(w.emitted('update:modelValue').at(-1)).toEqual(['a'])
  })

  it('click still selects (contract preserved)', async () => {
    const w = make('a')
    await w.findAll('[role="tab"]')[2].trigger('click')
    expect(w.emitted('update:modelValue').at(-1)).toEqual(['c'])
  })
})
