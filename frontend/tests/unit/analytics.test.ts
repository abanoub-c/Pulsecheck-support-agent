import { describe, expect, it } from 'vitest';
import { normalizeResolutionPercentages } from '../../src/lib/analytics';

describe('normalizeResolutionPercentages', () => {
  it.each([
    [{ solved: 1, total: 8 }, { solved: 13, unsolved: 87 }],
    [{ solved: 7, total: 8 }, { solved: 88, unsolved: 12 }],
    [{ solved: 0, total: 4 }, { solved: 0, unsolved: 100 }],
    [{ solved: 0, total: 0 }, { solved: 0, unsolved: 0 }],
  ])('returns complementary segments for %o', (counts, expected) => {
    const result = normalizeResolutionPercentages(counts);
    expect(result).toEqual(expected);
    if (counts.total > 0) expect(result.solved + result.unsolved).toBe(100);
  });
});
