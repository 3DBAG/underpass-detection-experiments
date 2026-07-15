import {
  isReviewStatus,
  isReviewTag,
  normalizeBuildingTags,
  normalizeReviewStatuses,
  type BuildingTag,
  type ReviewStatus,
  type ReviewTag,
} from "@/lib/review-tags";

export interface UnderpassReview {
  tags: ReviewStatus[];
  updatedAt?: string;
  automatic?: boolean;
}

export interface LegacyReviewStatus {
  tag: ReviewStatus;
  updatedAt?: string;
}

export interface BuildingReview {
  buildingId: string;
  tags: BuildingTag[];
  updatedAt?: string;
  underpasses: Record<string, UnderpassReview>;
  legacyStatus?: LegacyReviewStatus;
}

export interface TaggedReviewTarget {
  buildingId: string;
  underpassId?: string;
  legacy?: boolean;
}

interface SavedTagsResponse {
  buildingId: string;
  underpassId?: string;
  tags: unknown;
  updatedAt?: string;
  automatic?: boolean;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function buildingTagUrl(baseUrl: string, buildingId: string, underpassId?: string) {
  const root = `${baseUrl.replace(/\/$/, "")}/${encodeURIComponent(buildingId)}`;
  return underpassId ? `${root}/${encodeURIComponent(underpassId)}` : root;
}

async function responseError(response: Response) {
  try {
    const body = await response.json() as { error?: unknown };
    if (typeof body.error === "string") return body.error;
  } catch {
    // Fall through to the HTTP status when the server did not return JSON.
  }
  return `Tag request failed (${response.status}).`;
}

function parseBuildingReview(value: unknown): BuildingReview {
  if (
    !isObject(value) ||
    typeof value.buildingId !== "string" ||
    !isObject(value.underpasses)
  ) {
    throw new Error("The building-review response is invalid.");
  }
  const underpasses: Record<string, UnderpassReview> = {};
  for (const [underpassId, review] of Object.entries(value.underpasses)) {
    if (!isObject(review)) throw new Error("The underpass-review response is invalid.");
    underpasses[underpassId] = {
      tags: normalizeReviewStatuses(review.tags),
      updatedAt: typeof review.updatedAt === "string" ? review.updatedAt : undefined,
      automatic: review.automatic === true,
    };
  }
  let legacyStatus: LegacyReviewStatus | undefined;
  if (value.legacyStatus !== undefined) {
    if (!isObject(value.legacyStatus) || !isReviewStatus(value.legacyStatus.tag)) {
      throw new Error("The legacy-review response is invalid.");
    }
    legacyStatus = {
      tag: value.legacyStatus.tag,
      updatedAt:
        typeof value.legacyStatus.updatedAt === "string"
          ? value.legacyStatus.updatedAt
          : undefined,
    };
  }
  return {
    buildingId: value.buildingId,
    tags: normalizeBuildingTags(value.tags),
    updatedAt: typeof value.updatedAt === "string" ? value.updatedAt : undefined,
    underpasses,
    legacyStatus,
  };
}

export async function loadBuildingReview(
  baseUrl: string,
  buildingId: string,
  underpassIds: string[],
) {
  const url = new URL(buildingTagUrl(baseUrl, buildingId), window.location.href);
  underpassIds.forEach((underpassId) => url.searchParams.append("underpass", underpassId));
  const response = await fetch(url);
  if (!response.ok) throw new Error(await responseError(response));
  return parseBuildingReview(await response.json() as unknown);
}

export async function saveBuildingTags(
  baseUrl: string,
  buildingId: string,
  tags: BuildingTag[],
) {
  const response = await fetch(buildingTagUrl(baseUrl, buildingId), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tags: normalizeBuildingTags(tags) }),
  });
  if (!response.ok) throw new Error(await responseError(response));
  const body = await response.json() as SavedTagsResponse;
  return {
    tags: normalizeBuildingTags(body.tags),
    updatedAt: typeof body.updatedAt === "string" ? body.updatedAt : undefined,
  };
}

export async function saveUnderpassTags(
  baseUrl: string,
  buildingId: string,
  underpassId: string,
  tags: ReviewStatus[],
  options: { automatic?: boolean; resolveLegacy?: boolean } = {},
) {
  const response = await fetch(buildingTagUrl(baseUrl, buildingId, underpassId), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tags: normalizeReviewStatuses(tags),
      automatic: options.automatic === true,
      resolveLegacy: options.resolveLegacy === true,
    }),
  });
  if (!response.ok) throw new Error(await responseError(response));
  const body = await response.json() as SavedTagsResponse;
  return {
    tags: normalizeReviewStatuses(body.tags),
    updatedAt: typeof body.updatedAt === "string" ? body.updatedAt : undefined,
    automatic: body.automatic === true,
  };
}

export async function loadTaggedReviewTargets(baseUrl: string, tag: ReviewTag) {
  const url = new URL(baseUrl, window.location.href);
  url.searchParams.set("tag", tag);
  const response = await fetch(url);
  if (!response.ok) throw new Error(await responseError(response));
  const body: unknown = await response.json();
  if (
    !isObject(body) ||
    !isReviewTag(body.tag) ||
    !Array.isArray(body.objects)
  ) {
    throw new Error("The tagged-review response is invalid.");
  }
  return body.objects.map((target): TaggedReviewTarget => {
    if (
      !isObject(target) ||
      typeof target.buildingId !== "string" ||
      (target.underpassId !== undefined && typeof target.underpassId !== "string") ||
      (target.legacy !== undefined && typeof target.legacy !== "boolean")
    ) {
      throw new Error("The tagged-review target is invalid.");
    }
    return {
      buildingId: target.buildingId,
      underpassId: target.underpassId,
      legacy: target.legacy,
    };
  });
}
