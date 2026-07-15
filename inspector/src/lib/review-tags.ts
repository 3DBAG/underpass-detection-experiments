export const POINT_CLOUD_INSUFFICIENT_STATUS = "PointCloud insufficient" as const;

export const REVIEW_STATUSES = [
  "Approved",
  "Wrong elevation",
  POINT_CLOUD_INSUFFICIENT_STATUS,
  "Faulty underpass geometry",
] as const;

export const HIGHLIGHT_TAG = "Highlight" as const;
export const REVIEW_TAGS = [...REVIEW_STATUSES, HIGHLIGHT_TAG] as const;

export type ReviewStatus = (typeof REVIEW_STATUSES)[number];
export type BuildingTag = typeof HIGHLIGHT_TAG;
export type ReviewTag = (typeof REVIEW_TAGS)[number];

export function isReviewStatus(value: unknown): value is ReviewStatus {
  return typeof value === "string" && REVIEW_STATUSES.some((tag) => tag === value);
}

export function isReviewTag(value: unknown): value is ReviewTag {
  return typeof value === "string" && REVIEW_TAGS.some((tag) => tag === value);
}

export function normalizeReviewTags(value: unknown): ReviewTag[] {
  if (!Array.isArray(value) || !value.every(isReviewTag)) {
    throw new Error("Tags must be an array of supported tag names.");
  }
  const selected = new Set(value);
  const statusCount = REVIEW_STATUSES.filter((status) => selected.has(status)).length;
  if (statusCount > 1) {
    throw new Error("Only one review status can be assigned to a building.");
  }
  return REVIEW_TAGS.filter((tag) => selected.has(tag));
}

export function normalizeBuildingTags(value: unknown): BuildingTag[] {
  if (!Array.isArray(value) || !value.every((tag) => tag === HIGHLIGHT_TAG)) {
    throw new Error("Building tags may only contain Highlight.");
  }
  return value.includes(HIGHLIGHT_TAG) ? [HIGHLIGHT_TAG] : [];
}

export function normalizeReviewStatuses(value: unknown): ReviewStatus[] {
  if (!Array.isArray(value) || !value.every(isReviewStatus)) {
    throw new Error("Underpass tags must be supported review statuses.");
  }
  const selected = new Set(value);
  if (selected.size > 1) {
    throw new Error("Only one review status can be assigned to an underpass.");
  }
  return REVIEW_STATUSES.filter((tag) => selected.has(tag));
}
