import { describe, expect, it } from 'vitest'
import { CATEGORY_NAMES, LEVELS } from './types'

describe('ETF strategy presentation metadata', () => {
  it('keeps six distinct ETF categories', () => {
    expect(Object.keys(CATEGORY_NAMES)).toHaveLength(6)
    expect(new Set(Object.values(CATEGORY_NAMES)).size).toBe(6)
    expect(CATEGORY_NAMES.dividend_low_vol).toBe('红利低波')
    expect(CATEGORY_NAMES.bond).toBe('债券')
  })
  it('shows all three buy and three sell observation levels', () => {
    expect(LEVELS).toEqual(['B1','B2','B3','S1','S2','S3'])
  })
})
