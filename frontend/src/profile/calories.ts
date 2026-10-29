import type { Energy, Health } from './types'

const empty = (): Energy => ({ bmr: null, tdee: null, intake: null })
function decimal10(value: string | null, low: bigint, high: bigint): bigint | null {
  if (value === null || !/^(0|[1-9][0-9]{0,2})(\.[0-9])?$/.test(value)) return null
  const [whole = '', fraction = '0'] = value.split('.')
  const number = BigInt(whole) * 10n + BigInt(fraction)
  return number >= low * 10n && number <= high * 10n ? number : null
}
function rounded(n: bigint, d: bigint): number {
  return Number((2n * n + d) / (2n * d))
}
export function calculate(health: Health): Energy {
  const result = empty()
  const weight = decimal10(health.weight, 20n, 350n)
  const height = decimal10(health.height, 100n, 250n)
  if (weight === null || height === null || health.age === null || !Number.isInteger(health.age) || health.age < 19 || health.age > 59 || !['male', 'female'].includes(health.formula ?? '')) return result
  const n = 40n * weight + 25n * height - 200n * BigInt(health.age) + 40n * (health.formula === 'male' ? 5n : -161n)
  if (n <= 0n) return result
  result.bmr = rounded(n, 40n)
  const ratios: Record<string, readonly [bigint, bigint]> = { low: [3n, 2n], medium: [7n, 4n], high: [21n, 10n] }
  const ratio = ratios[health.activity ?? '']
  if (ratio) result.tdee = result.intake = rounded(n * ratio[0], 40n * ratio[1])
  return result
}
