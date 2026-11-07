/** Stable record state; signed media capabilities naturally change with time. */
export function unchangedRecord(value) {
  const copy = structuredClone(value)
  const strip = item => {
    if (item && typeof item === 'object') {
      delete item.url; delete item.expires_at
      for (const nested of Object.values(item)) strip(nested)
    }
  }
  strip(copy)
  return copy
}
