/** Small seeded PRNG so the demo fixtures are identical on every load. */
export type Rand = () => number;

function fnv1a(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

function mulberry32(seed: number): Rand {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function rngFor(...parts: (string | number)[]): Rand {
  return mulberry32(fnv1a(parts.join("|")));
}

export function between(r: Rand, lo: number, hi: number): number {
  return lo + r() * (hi - lo);
}

export function intBetween(r: Rand, lo: number, hi: number): number {
  return Math.floor(between(r, lo, hi + 1));
}

export function hexId(r: Rand, len = 12): string {
  let s = "";
  for (let i = 0; i < len; i++) s += Math.floor(r() * 16).toString(16);
  return s;
}

export const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
