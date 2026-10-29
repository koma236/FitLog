import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { workoutEnergy } from './calories'
import vectors from './calorie-vectors.json'

describe('independent MET estimates', () => {
  it('matches fixed hand calculated values, including half-up ties', () => {
    expect(createHash('sha256').update(readFileSync('src/workouts/calorie-vectors.json')).digest('hex')).toBe('a0fb973ce4f6bcc907508602ffeeebb05dd2da95caa118f54bead5e14ecc17e3')
    for (const row of vectors) expect(workoutEnergy(row.weight, 30, row.minutes, row.kind)).toBe(row.kcal)
  })
  it('requires only weight, eligible age, minutes and kind', () => {
    expect(workoutEnergy('60.0', 18, 30, 'general')).toBeNull()
    expect(workoutEnergy('60.0', 60, 30, 'general')).toBeNull()
    expect(workoutEnergy(null, 30, 30, 'general')).toBeNull()
    expect(workoutEnergy('60.0', 19, 30, 'general')).toBe(105)
    expect(workoutEnergy('60.0', 59, 30, 'general')).toBe(105)
  })
})
