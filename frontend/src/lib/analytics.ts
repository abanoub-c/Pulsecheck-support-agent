export function normalizeResolutionPercentages({ solved, total }: { solved: number; total: number }) {
  if (total <= 0) return { solved: 0, unsolved: 0 };
  const solvedPercent = Math.min(100, Math.max(0, Math.round((solved / total) * 100)));
  return { solved: solvedPercent, unsolved: 100 - solvedPercent };
}
