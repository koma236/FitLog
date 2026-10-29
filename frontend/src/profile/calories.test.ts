import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { expect, it } from 'vitest'
import { calculate } from './calories'
import type { Energy, Health } from './types'

it('matches the independent hand-calculated shared table, including double-rounding traps', () => {
  const raw = readFileSync('src/profile/calorie-vectors.json')
  expect(createHash('sha256').update(raw).digest('hex')).toBe('1821ed52979638275e10012d7a3082cc54f26554d3c8c9c8a55e44529411febc')
  const vectors = JSON.parse(raw.toString()) as { health: Health; energy: Energy }[]
  for (const vector of vectors) expect(calculate(vector.health)).toEqual(vector.energy)
})
