export function workoutEnergy(weight: string | null, age: number | null, minutes: number | null, kind: string | null): number | null {
  const met: Record<string, bigint> = { general: 35n, squat: 50n, vigorous: 60n }
  if (weight === null || !/^(0|[1-9][0-9]{0,2})(\.[0-9])?$/.test(weight) || age === null || !Number.isInteger(age) || age < 19 || age > 59 || minutes === null || !Number.isInteger(minutes) || minutes < 1 || minutes > 240 || kind === null || !Object.hasOwn(met, kind)) return null
  const [whole = '0', fraction = '0'] = weight.split('.')
  const w = BigInt(whole) * 10n + BigInt(fraction)
  if (w < 200n || w > 3500n) return null
  const numerator = (met[kind] ?? 0n) * w * BigInt(minutes)
  return Number((2n * numerator + 6000n) / 12000n)
}
