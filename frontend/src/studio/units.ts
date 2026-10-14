import type { PhysicalQuantity, UnitConversion } from '@/api/contracts'

/** Engineering units offered per quantity; the first is the platform's normalized unit. */
export const UNITS: Record<PhysicalQuantity, string[]> = {
  SPEED: ['rpm', 'm/s', 'mm/s'],
  TORQUE: ['N*m', '%rated'],
  DURATION: ['s', 'ms'],
  POSITION: ['mm', 'm'],
  CURRENT: ['A', 'mA'],
  PRESSURE: ['bar', 'kPa', 'MPa'],
  VIBRATION: ['mm/s', 'g'],
  OTHER: [''],
}

const SCALE: Record<string, number> = {
  'mm/s>m/s': 0.001,
  'm/s>mm/s': 1000,
  'ms>s': 0.001,
  's>ms': 1000,
  'm>mm': 1000,
  'mm>m': 0.001,
  'mA>A': 0.001,
  'A>mA': 1000,
  'kPa>bar': 0.01,
  'MPa>bar': 10,
  'bar>kPa': 100,
}

/**
 * Suggested scale for a unit pair, or null when it depends on the equipment (e.g. %rated torque
 * needs the drive's rated torque) and the user must enter it.
 */
export function suggestedScale(source: string, target: string): number | null {
  if (source === target) return 1
  return SCALE[`${source}>${target}`] ?? null
}

export function convert(value: number, c: Pick<UnitConversion, 'scale' | 'offset'>): number {
  return value * (c.scale ?? 1) + (c.offset ?? 0)
}
