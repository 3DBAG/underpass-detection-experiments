import { useEffect, useMemo, useRef, useState } from "react";
import {
  Box,
  Building2,
  Cloud,
  CircleHelp,
  ChevronLeft,
  ChevronRight,
  Database,
  Eye,
  EyeOff,
  Focus,
  ListFilter,
  LoaderCircle,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Star,
  Tag,
  TriangleAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  SceneViewer,
  type PickedWorldPoint,
  type PointCloudStatus,
  type SceneViewerHandle,
} from "@/components/scene-viewer";
import {
  availableLods,
  createBuildingScene,
  disposeBuildingScene,
  underpassIdFromAttributes,
  underpassesForRecord,
  UNDERPASS_CANDIDATE_PEAKS_ATTRIBUTE,
  type BuildingScene,
} from "@/lib/cityjson-mesh";
import {
  loadBuildingById,
  normalizeBuildingId,
  type BuildingRecord,
} from "@/lib/fcb";
import {
  loadBuildingReview,
  loadTaggedReviewTargets,
  saveBuildingTags,
  saveUnderpassTags,
  type BuildingReview,
  type TaggedReviewTarget,
} from "@/lib/tag-api";
import {
  HIGHLIGHT_TAG,
  POINT_CLOUD_INSUFFICIENT_STATUS,
  REVIEW_STATUSES,
  REVIEW_TAGS,
  type ReviewStatus,
  type ReviewTag,
} from "@/lib/review-tags";

const FCB_URL = import.meta.env.VITE_FCB_URL ?? "/data/city.fcb";
const COPC_URL = import.meta.env.VITE_COPC_URL ?? "/data/merged.copc";
const UNDERPASS_URL = import.meta.env.VITE_UNDERPASS_URL ?? "/data/underpasses.json";
const TAG_API_URL = import.meta.env.VITE_TAG_API_URL ?? "/api/tags";
const VALUE_FORMAT = new Intl.NumberFormat("en", { maximumFractionDigits: 3 });
const COUNT_FORMAT = new Intl.NumberFormat("en", {
  notation: "compact",
  maximumFractionDigits: 1,
});
const COORDINATE_FORMAT = new Intl.NumberFormat("en", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});
const EMPTY_POINT_STATUS: PointCloudStatus = {
  loading: false,
  progress: 0,
  displayedPoints: 0,
};

type LoadState = "idle" | "loading" | "ready" | "error";
type TagState = "idle" | "loading" | "ready" | "saving" | "error";
type CandidatePeak = Record<string, unknown>;

const PEAK_COLUMN_ORDER = [
  "display_order",
  "peak_idx",
  "selected",
  "elevation",
  "z_min",
  "z_max",
  "area_m2",
  "largest_contiguous_area_m2",
  "point_count",
  "raw_count",
  "smoothed_count",
];

const PEAK_COLUMN_LABELS: Record<string, string> = {
  display_order: "Order",
  peak_idx: "Peak",
  selected: "Selected",
  elevation: "Elevation",
  z_min: "Z min",
  z_max: "Z max",
  area_m2: "Area m²",
  largest_contiguous_area_m2: "Largest area m²",
  point_count: "Points",
  raw_count: "Raw points",
  smoothed_count: "Smoothed points",
};

function buildingFromUrl() {
  return new URLSearchParams(window.location.search).get("building") ?? "";
}

function underpassFromUrl() {
  return new URLSearchParams(window.location.search).get("underpass") ?? undefined;
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "Not set";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return VALUE_FORMAT.format(value);
  if (typeof value === "object") return JSON.stringify(value) ?? String(value);
  return String(value);
}

function formatPickedAttribute(value: unknown) {
  const formatted = formatValue(value);
  return formatted.length > 160 ? `${formatted.slice(0, 157)}…` : formatted;
}

function parseCandidatePeaks(value: unknown): CandidatePeak[] | undefined {
  let parsed = value;
  if (typeof value === "string") {
    try {
      parsed = JSON.parse(value) as unknown;
    } catch {
      return undefined;
    }
  }
  if (
    !Array.isArray(parsed) ||
    !parsed.every((peak) => peak !== null && typeof peak === "object" && !Array.isArray(peak))
  ) {
    return undefined;
  }
  return parsed as CandidatePeak[];
}

function candidatePeakColumns(peaks: CandidatePeak[]) {
  const available = new Set(peaks.flatMap((peak) => Object.keys(peak)));
  return [
    ...PEAK_COLUMN_ORDER.filter((column) => available.delete(column)),
    ...[...available].sort(),
  ];
}

function CandidatePeaksTable({ peaks }: { peaks: CandidatePeak[] }) {
  if (peaks.length === 0) {
    return <span className="candidate-peaks-empty">No candidate peaks</span>;
  }
  const columns = candidatePeakColumns(peaks);
  return (
    <div className="candidate-peaks-table-wrap">
      <table className="candidate-peaks-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column} title={column} scope="col">
                {PEAK_COLUMN_LABELS[column] ?? column.replaceAll("_", " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {peaks.map((peak, index) => (
            <tr
              key={typeof peak.peak_idx === "number" ? peak.peak_idx : index}
              className={peak.selected === true ? "is-selected" : undefined}
            >
              {columns.map((column) => (
                <td key={column}>{formatValue(peak[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatCount(value?: number) {
  if (value === undefined) return "--";
  return COUNT_FORMAT.format(value);
}

function formatCoordinate(value: number) {
  return COORDINATE_FORMAT.format(value);
}

function LabelRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex min-h-8 items-center justify-between gap-4 border-b border-border/70 py-1.5 text-xs last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 text-right font-medium text-foreground">{value}</span>
    </div>
  );
}

export default function App() {
  const initialId = buildingFromUrl();
  const [inputId, setInputId] = useState(initialId);
  const [buildingId, setBuildingId] = useState(initialId);
  const [record, setRecord] = useState<BuildingRecord>();
  const [underpassIds, setUnderpassIds] = useState<string[]>();
  const [underpassError, setUnderpassError] = useState<string>();
  const [review, setReview] = useState<BuildingReview>();
  const [selectedUnderpassId, setSelectedUnderpassId] = useState(underpassFromUrl());
  const [tagState, setTagState] = useState<TagState>("idle");
  const [tagError, setTagError] = useState<string>();
  const [tagListOpen, setTagListOpen] = useState(false);
  const [tagListTag, setTagListTag] = useState<ReviewTag>(REVIEW_STATUSES[0]);
  const [taggedTargets, setTaggedTargets] = useState<TaggedReviewTarget[]>([]);
  const [tagListState, setTagListState] = useState<LoadState>("idle");
  const [tagListError, setTagListError] = useState<string>();
  const [tagListRevision, setTagListRevision] = useState(0);
  const [loadState, setLoadState] = useState<LoadState>(initialId ? "loading" : "idle");
  const [error, setError] = useState<string>();
  const [lod, setLod] = useState<string>();
  const [modelVisible, setModelVisible] = useState(true);
  const [outerCeilingOnly, setOuterCeilingOnly] = useState(false);
  const [pointCloudVisible, setPointCloudVisible] = useState(true);
  const [pickedPoint, setPickedPoint] = useState<PickedWorldPoint>();
  const [pointSize, setPointSize] = useState(1.7);
  const [pointBudget, setPointBudget] = useState(1_500_000);
  const [pointStatus, setPointStatus] = useState<PointCloudStatus>(EMPTY_POINT_STATUS);
  const viewerRef = useRef<SceneViewerHandle>(null);
  const requestRef = useRef(0);
  const tagRequestRef = useRef(0);
  const tagListRequestRef = useRef(0);
  const keyboardActionsRef = useRef<{
    toggleStatus: (status: ReviewStatus) => void;
    cycleModel: () => void;
    previous: () => void;
    next: () => void;
  } | undefined>(undefined);

  useEffect(() => {
    const onPopState = () => {
      const id = buildingFromUrl();
      setInputId(id);
      setBuildingId(id);
      setSelectedUnderpassId(underpassFromUrl());
      setPickedPoint(undefined);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch(UNDERPASS_URL)
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Could not load underpass navigation (${response.status}).`);
        }
        const value: unknown = await response.json();
        if (!Array.isArray(value) || !value.every((id) => typeof id === "string")) {
          throw new Error("The underpass navigation file is invalid.");
        }
        return value;
      })
      .then((ids) => {
        if (!cancelled) setUnderpassIds(ids);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setUnderpassError(reason instanceof Error ? reason.message : String(reason));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const request = ++requestRef.current;
    if (!buildingId) {
      setRecord(undefined);
      setLoadState("idle");
      setPointStatus(EMPTY_POINT_STATUS);
      return;
    }

    setRecord(undefined);
    setLoadState("loading");
    setError(undefined);
    setPointStatus(EMPTY_POINT_STATUS);
    loadBuildingById(FCB_URL, buildingId)
      .then((result) => {
        if (request !== requestRef.current) return;
        setRecord(result);
        setLod(availableLods(result).at(-1));
        setLoadState("ready");
      })
      .catch((reason: unknown) => {
        if (request !== requestRef.current) return;
        setRecord(undefined);
        setError(reason instanceof Error ? reason.message : String(reason));
        setLoadState("error");
      });
  }, [buildingId]);

  const underpasses = useMemo(
    () => (record ? underpassesForRecord(record) : []),
    [record],
  );

  useEffect(() => {
    if (!record) {
      setSelectedUnderpassId(undefined);
      return;
    }
    const requested = underpassFromUrl();
    const nextId = underpasses.some(({ id }) => id === requested)
      ? requested
      : underpasses[0]?.id;
    setSelectedUnderpassId(nextId);
    const url = new URL(window.location.href);
    if (nextId) url.searchParams.set("underpass", nextId);
    else url.searchParams.delete("underpass");
    window.history.replaceState({}, "", url);
  }, [record, underpasses]);

  useEffect(() => {
    const request = ++tagRequestRef.current;
    if (!record) {
      setReview(undefined);
      setTagState("idle");
      setTagError(undefined);
      return;
    }

    setReview(undefined);
    setTagState("loading");
    setTagError(undefined);
    void (async () => {
      try {
        const loadedReview = await loadBuildingReview(
          TAG_API_URL,
          record.id,
          underpasses.map(({ id }) => id),
        );
        if (request !== tagRequestRef.current) return;
        const defaults = underpasses.filter(
          ({ id, hasCandidatePeaks }) =>
            !hasCandidatePeaks && loadedReview.underpasses[id] === undefined,
        );
        const savedDefaults = await Promise.all(
          defaults.map(async ({ id }) => ({
            id,
            review: await saveUnderpassTags(
              TAG_API_URL,
              record.id,
              id,
              [POINT_CLOUD_INSUFFICIENT_STATUS],
              { automatic: true, resolveLegacy: false },
            ),
          })),
        );
        if (request !== tagRequestRef.current) return;
        const buildingReview = { ...loadedReview, underpasses: { ...loadedReview.underpasses } };
        savedDefaults.forEach(({ id, review: underpassReview }) => {
          buildingReview.underpasses[id] = underpassReview;
        });
        setReview(buildingReview);
        setTagState("ready");
        setTagListRevision((revision) => revision + 1);
      } catch (reason: unknown) {
        if (request !== tagRequestRef.current) return;
        setTagError(reason instanceof Error ? reason.message : String(reason));
        setTagState("error");
      }
    })();
  }, [record, underpasses]);

  useEffect(() => {
    const request = ++tagListRequestRef.current;
    if (!tagListOpen) {
      setTagListState("idle");
      setTagListError(undefined);
      return;
    }

    setTagListState("loading");
    setTagListError(undefined);
    loadTaggedReviewTargets(TAG_API_URL, tagListTag)
      .then((targets) => {
        if (request !== tagListRequestRef.current) return;
        setTaggedTargets(targets);
        setTagListState("ready");
      })
      .catch((reason: unknown) => {
        if (request !== tagListRequestRef.current) return;
        setTaggedTargets([]);
        setTagListError(reason instanceof Error ? reason.message : String(reason));
        setTagListState("error");
      });
  }, [tagListOpen, tagListRevision, tagListTag]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.isContentEditable ||
          target.matches("input, select, textarea, [role='slider']"))
      ) {
        return;
      }

      const statusIndex = Number(event.key) - 1;
      if (Number.isInteger(statusIndex) && REVIEW_STATUSES[statusIndex]) {
        event.preventDefault();
        keyboardActionsRef.current?.toggleStatus(REVIEW_STATUSES[statusIndex]);
      } else if (event.key.toLowerCase() === "t") {
        event.preventDefault();
        keyboardActionsRef.current?.cycleModel();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        keyboardActionsRef.current?.previous();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        keyboardActionsRef.current?.next();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const buildingSceneResult = useMemo<{ scene?: BuildingScene; error?: string }>(() => {
    if (!record) return {};
    try {
      return { scene: createBuildingScene(record, lod) };
    } catch (reason) {
      return { error: reason instanceof Error ? reason.message : String(reason) };
    }
  }, [lod, record]);
  const buildingScene = buildingSceneResult.scene;
  const displayedError = buildingSceneResult.error ?? error ?? underpassError;

  useEffect(() => {
    return () => {
      if (buildingScene) disposeBuildingScene(buildingScene);
    };
  }, [buildingScene]);

  const attributeGroups = useMemo(() => {
    if (!record) return [];
    const objectOrder: Record<string, number> = { Building: 0, BuildingPart: 1 };
    return Object.entries(record.feature.CityObjects)
      .map(([id, object]) => ({
        id,
        type: object.type,
        attributes: Object.entries(object.attributes ?? {}).sort(([a], [b]) =>
          a.localeCompare(b),
        ),
      }))
      .filter(({ attributes }) => attributes.length > 0)
      .sort((a, b) =>
        (objectOrder[a.type] ?? 2) - (objectOrder[b.type] ?? 2) ||
        a.id.localeCompare(b.id),
      );
  }, [record]);
  const lods = useMemo(() => (record ? availableLods(record) : []), [record]);
  const underpassIndex = useMemo(
    () => (record && underpassIds ? underpassIds.indexOf(record.id) : -1),
    [record, underpassIds],
  );

  function submitBuilding(event: React.FormEvent) {
    event.preventDefault();
    const normalized = normalizeBuildingId(inputId);
    if (!normalized) return;
    selectBuilding(normalized, "push");
  }

  function selectBuilding(
    id: string,
    historyMode: "push" | "replace" = "replace",
    underpassId?: string,
  ) {
    const url = new URL(window.location.href);
    url.searchParams.set("building", id);
    if (underpassId) url.searchParams.set("underpass", underpassId);
    else url.searchParams.delete("underpass");
    if (historyMode === "push") window.history.pushState({}, "", url);
    else window.history.replaceState({}, "", url);
    setInputId(id);
    setBuildingId(id);
    setSelectedUnderpassId(underpassId);
    setPickedPoint(undefined);
  }

  function selectUnderpassBuilding(index: number) {
    const id = underpassIds?.[index];
    if (!id) return;
    selectBuilding(id);
  }

  function selectUnderpassSurface(underpassId: string) {
    if (!underpasses.some(({ id }) => id === underpassId)) return;
    const url = new URL(window.location.href);
    url.searchParams.set("underpass", underpassId);
    window.history.replaceState({}, "", url);
    setSelectedUnderpassId(underpassId);
  }

  function handlePickedPoint(point: PickedWorldPoint) {
    setPickedPoint(point);
    const underpassId = underpassIdFromAttributes(point.semanticSurface?.attributes);
    if (underpassId) selectUnderpassSurface(underpassId);
  }

  function persistUnderpassStatus(
    nextTags: ReviewStatus[],
    options: { resolveLegacy?: boolean } = {},
  ) {
    if (!record || !review || !selectedUnderpassId || tagState === "saving") return;
    const request = ++tagRequestRef.current;
    const buildingIdToSave = record.id;
    const underpassIdToSave = selectedUnderpassId;
    const previousReview = review;
    const nextUnderpasses = { ...review.underpasses };
    nextUnderpasses[underpassIdToSave] = { tags: nextTags, automatic: false };
    setReview({
      ...review,
      underpasses: nextUnderpasses,
      legacyStatus: options.resolveLegacy ? undefined : review.legacyStatus,
    });
    setTagState("saving");
    setTagError(undefined);
    void saveUnderpassTags(
      TAG_API_URL,
      buildingIdToSave,
      underpassIdToSave,
      nextTags,
      { resolveLegacy: options.resolveLegacy === true },
    )
      .then((savedReview) => {
        if (request !== tagRequestRef.current) return;
        setReview((current) => {
          if (!current) return current;
          const underpassReviews = { ...current.underpasses };
          underpassReviews[underpassIdToSave] = savedReview;
          return {
            ...current,
            underpasses: underpassReviews,
            legacyStatus: options.resolveLegacy ? undefined : current.legacyStatus,
          };
        });
        setTagState("ready");
        setTagListRevision((revision) => revision + 1);
      })
      .catch((reason: unknown) => {
        if (request !== tagRequestRef.current) return;
        setReview(previousReview);
        setTagError(reason instanceof Error ? reason.message : String(reason));
        setTagState("error");
      });
  }

  function toggleReviewStatus(status: ReviewStatus) {
    persistUnderpassStatus(reviewStatus === status ? [] : [status]);
  }

  function toggleHighlight() {
    if (!record || !review || tagState === "saving") return;
    const request = ++tagRequestRef.current;
    const previousReview = review;
    const nextTags = review.tags.includes(HIGHLIGHT_TAG) ? [] : [HIGHLIGHT_TAG];
    setReview({ ...review, tags: nextTags });
    setTagState("saving");
    setTagError(undefined);
    void saveBuildingTags(TAG_API_URL, record.id, nextTags)
      .then((savedReview) => {
        if (request !== tagRequestRef.current) return;
        setReview((current) => current && { ...current, ...savedReview });
        setTagState("ready");
        setTagListRevision((revision) => revision + 1);
      })
      .catch((reason: unknown) => {
        if (request !== tagRequestRef.current) return;
        setReview(previousReview);
        setTagError(reason instanceof Error ? reason.message : String(reason));
        setTagState("error");
      });
  }

  function cycleModelVisibility() {
    if (!modelVisible) {
      setModelVisible(true);
      setOuterCeilingOnly(false);
    } else if (!outerCeilingOnly) {
      setOuterCeilingOnly(true);
    } else {
      setModelVisible(false);
    }
  }

  const selectedUnderpass = underpasses.find(({ id }) => id === selectedUnderpassId);
  const selectedUnderpassIndex = selectedUnderpass
    ? underpasses.indexOf(selectedUnderpass)
    : -1;
  const reviewStatus = selectedUnderpassId
    ? review?.underpasses[selectedUnderpassId]?.tags[0]
    : undefined;
  const selectedUnderpassReview = selectedUnderpassId
    ? review?.underpasses[selectedUnderpassId]
    : undefined;
  const highlightSelected = review?.tags.includes(HIGHLIGHT_TAG) ?? false;
  const tagsDisabled = !record || !review || tagState === "loading" || tagState === "saving";
  const reviewStatusesDisabled = tagsDisabled || !selectedUnderpass;
  const canGoPrevious = loadState !== "loading" && underpassIndex > 0;
  const canGoNext =
    loadState !== "loading" &&
    underpassIds !== undefined &&
    underpassIds.length > 0 &&
    underpassIndex + 1 < underpassIds.length;

  keyboardActionsRef.current = {
    toggleStatus: (status) => {
      if (!reviewStatusesDisabled) toggleReviewStatus(status);
    },
    cycleModel: cycleModelVisibility,
    previous: () => {
      if (canGoPrevious) selectUnderpassBuilding(underpassIndex - 1);
    },
    next: () => {
      if (canGoNext) selectUnderpassBuilding(underpassIndex + 1);
    },
  };

  return (
    <TooltipProvider delayDuration={350}>
      <main className="app-shell">
        <header className="app-header">
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold">Alignment Inspector</h1>
            <p className="truncate text-[11px] text-muted-foreground">City model / point cloud</p>
          </div>

          <form onSubmit={submitBuilding} className="search-form">
            <Search className="absolute left-3 size-4 text-muted-foreground" />
            <Input
              value={inputId}
              onChange={(event) => setInputId(event.target.value)}
              placeholder="NL.IMBAG.Pand.0363100012061167"
              aria-label="Building ID"
              className="h-9 pl-9 pr-20 font-mono text-xs"
            />
            <Button type="submit" size="sm" className="absolute right-1 h-7" disabled={loadState === "loading"}>
              {loadState === "loading" ? <LoaderCircle className="animate-spin" /> : "Load"}
            </Button>
          </form>

          <div className="header-actions">
            <div className="hidden items-center gap-2 text-xs text-muted-foreground md:flex">
              <span className={`status-dot ${loadState === "error" ? "bg-red-500" : loadState === "ready" ? "bg-emerald-500" : "bg-zinc-400"}`} />
              {loadState === "ready" ? "Building loaded" : loadState === "error" ? "Load failed" : "Ready"}
            </div>
            <details className="help-menu">
              <summary aria-label="Open keyboard shortcuts and tag help">
                <CircleHelp />
              </summary>
              <div className="help-popover">
                <section>
                  <h2>Keyboard shortcuts</h2>
                  <dl className="shortcut-list">
                    <div><dt><kbd>1</kbd></dt><dd>Toggle Approved</dd></div>
                    <div><dt><kbd>2</kbd></dt><dd>Toggle Wrong elevation</dd></div>
                    <div><dt><kbd>3</kbd></dt><dd>Toggle PointCloud insufficient</dd></div>
                    <div><dt><kbd>4</kbd></dt><dd>Toggle Faulty underpass geometry</dd></div>
                    <div><dt><kbd>T</kbd></dt><dd>Full model → outer ceiling → hidden</dd></div>
                    <div><dt><kbd>←</kbd><kbd>→</kbd></dt><dd>Previous / next underpass</dd></div>
                  </dl>
                  <p className="shortcut-note">Numbered tags apply to the selected underpass. Missing peak-detection data defaults to PointCloud insufficient and remains user-overridable.</p>
                </section>
                <section>
                  <h2>Review tags</h2>
                  <dl className="tag-help-list">
                    <div><dt data-tag="Approved">Approved</dt><dd>The result is acceptable.</dd></div>
                    <div><dt data-tag="Wrong elevation">Wrong elevation</dt><dd>The underpass surface is at the wrong height.</dd></div>
                    <div><dt data-tag="PointCloud insufficient">PointCloud insufficient</dt><dd>There are not enough source points to assess the result.</dd></div>
                    <div><dt data-tag="Faulty underpass geometry">Faulty underpass geometry</dt><dd>The generated underpass shape or topology is incorrect.</dd></div>
                    <div><dt data-tag="Highlight">Highlight</dt><dd>Bookmark the building for extra attention; combines with any status.</dd></div>
                  </dl>
                </section>
                <p className="help-tip">Click the model or point cloud to inspect its world coordinates. Double-click to center the view on that point.</p>
              </div>
            </details>
          </div>
        </header>

        <section className="viewer-region">
          <SceneViewer
            ref={viewerRef}
            copcUrl={COPC_URL}
            building={buildingScene}
            modelVisible={modelVisible}
            outerCeilingOnly={outerCeilingOnly}
            pointCloudVisible={pointCloudVisible}
            selectedUnderpassId={selectedUnderpassId}
            pointSize={pointSize}
            pointBudget={pointBudget}
            onPickPoint={handlePickedPoint}
            onPointCloudStatus={setPointStatus}
            onError={setError}
          />

          {tagListOpen ? (
            <aside className="tag-list-panel" aria-label="Objects by review tag">
              <div className="tag-list-header">
                <div>
                  <span className="tag-list-title"><ListFilter /> Tagged objects</span>
                  <span className="tag-list-count">
                    {tagListState === "loading"
                      ? "Loading…"
                      : `${taggedTargets.length} ${taggedTargets.length === 1 ? "review" : "reviews"}`}
                  </span>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => setTagListOpen(false)}
                  aria-label="Close tagged objects panel"
                >
                  <PanelLeftClose />
                </Button>
              </div>
              <div className="tag-list-filters" aria-label="Filter objects by tag">
                {REVIEW_TAGS.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    className="tag-list-filter"
                    data-tag={tag}
                    data-selected={tagListTag === tag}
                    onClick={() => setTagListTag(tag)}
                    aria-pressed={tagListTag === tag}
                  >
                    {tag}
                  </button>
                ))}
              </div>
              <div className="tag-list-body">
                {tagListState === "loading" ? (
                  <div className="tag-list-message"><LoaderCircle className="animate-spin" /> Loading objects</div>
                ) : tagListError ? (
                  <div className="tag-list-message tag-list-error" role="alert">{tagListError}</div>
                ) : taggedTargets.length === 0 ? (
                  <div className="tag-list-message">No reviews have this tag.</div>
                ) : (
                  taggedTargets.map((target, index) => (
                    <button
                      key={`${target.buildingId}:${target.underpassId ?? (target.legacy ? "legacy" : "building")}`}
                      type="button"
                      className="tag-list-item"
                      data-active={
                        record?.id === target.buildingId &&
                        (target.underpassId === undefined || target.underpassId === selectedUnderpassId)
                      }
                      onClick={() => selectBuilding(
                        target.buildingId,
                        "replace",
                        target.underpassId,
                      )}
                      aria-current={
                        record?.id === target.buildingId &&
                        (target.underpassId === undefined || target.underpassId === selectedUnderpassId)
                          ? "true"
                          : undefined
                      }
                    >
                      <span>{index + 1}</span>
                      <span className="tag-list-target">
                        <span title={target.buildingId}>{target.buildingId}</span>
                        {(target.underpassId || target.legacy) && (
                          <small>
                            {target.underpassId
                              ? `Underpass ${target.underpassId}`
                              : "Legacy status · underpass not assigned"}
                          </small>
                        )}
                      </span>
                    </button>
                  ))
                )}
              </div>
            </aside>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  className="tag-list-toggle"
                  type="button"
                  variant="secondary"
                  size="icon"
                  onClick={() => setTagListOpen(true)}
                >
                  <PanelLeftOpen />
                  <span className="sr-only">Open tagged objects panel</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>Browse objects by tag</TooltipContent>
            </Tooltip>
          )}

          <div className="viewer-toolbar">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="secondary" size="icon" onClick={() => viewerRef.current?.resetCamera()} disabled={!buildingScene}>
                  <Focus />
                  <span className="sr-only">Frame building</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>Frame building</TooltipContent>
            </Tooltip>
          </div>

          {pickedPoint && (
            <div className="pick-readout" aria-live="polite">
              <div className="pick-readout-header">
                <span>Picked point</span>
                <span>EPSG:7415</span>
              </div>
              <dl className="pick-coordinate-grid">
                <dt>X</dt><dd>{formatCoordinate(pickedPoint.x)}</dd>
                <dt>Y</dt><dd>{formatCoordinate(pickedPoint.y)}</dd>
                <dt>Z</dt><dd>{formatCoordinate(pickedPoint.z)}</dd>
              </dl>
              {pickedPoint.semanticSurface && (
                <div className="pick-surface">
                  <div className="pick-surface-header">
                    <span>{pickedPoint.semanticSurface.type}</span>
                    <span>{Object.keys(pickedPoint.semanticSurface.attributes).length} attributes</span>
                  </div>
                  <dl className="pick-surface-attributes">
                    {Object.entries(pickedPoint.semanticSurface.attributes)
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([key, value]) => {
                        const candidatePeaks = key === UNDERPASS_CANDIDATE_PEAKS_ATTRIBUTE
                          ? parseCandidatePeaks(value)
                          : undefined;
                        if (candidatePeaks) {
                          return (
                            <div key={key} className="pick-candidate-attribute">
                              <dt title={key}>{key}</dt>
                              <dd><CandidatePeaksTable peaks={candidatePeaks} /></dd>
                            </div>
                          );
                        }
                        const fullValue = formatValue(value);
                        return (
                          <div key={key}>
                            <dt title={key}>{key}</dt>
                            <dd title={fullValue}>{formatPickedAttribute(value)}</dd>
                          </div>
                        );
                      })}
                  </dl>
                </div>
              )}
            </div>
          )}

          {loadState === "idle" && (
            <div className="viewer-empty">
              <Building2 className="size-8 text-muted-foreground" />
              <span className="text-sm font-medium">Enter a building ID</span>
            </div>
          )}
          {loadState === "loading" && (
            <div className="viewer-loading">
              <LoaderCircle className="size-5 animate-spin" />
              <span>Loading building</span>
            </div>
          )}
          {displayedError && (
            <div className="error-banner" role="alert">
              <TriangleAlert className="size-4 shrink-0" />
              <span>{displayedError}</span>
              {!buildingSceneResult.error && (
                <button
                  onClick={() => {
                    setError(undefined);
                    setUnderpassError(undefined);
                  }}
                  className="ml-auto"
                  aria-label="Dismiss error"
                >×</button>
              )}
            </div>
          )}
        </section>

        <aside className="inspector-panel">
          <div className="border-b border-border px-4 py-3">
            <div className="flex items-start gap-2">
              <Database className="mt-0.5 size-4 shrink-0 text-primary" />
              <div className="min-w-0">
                <p className="truncate font-mono text-xs font-medium">{record?.id ?? "No building selected"}</p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">EPSG:7415 · RD / NAP</p>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => selectUnderpassBuilding(underpassIndex - 1)}
                disabled={!canGoPrevious}
              >
                <ChevronLeft />
                Previous
              </Button>
              <span className="min-w-20 text-center text-[10px] tabular-nums text-muted-foreground">
                {underpassIds === undefined
                  ? underpassError ? "Unavailable" : "Loading…"
                  : underpassIndex >= 0
                    ? `${underpassIndex + 1} / ${underpassIds.length}`
                    : `${underpassIds.length} underpasses`}
              </span>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => selectUnderpassBuilding(underpassIndex + 1)}
                disabled={!canGoNext}
              >
                Next
                <ChevronRight />
              </Button>
            </div>
            <div className="review-tag-panel">
              <span className="review-tag-label"><Tag /> Review</span>
              {underpasses.length > 1 && selectedUnderpass && (
                <div className="underpass-selector">
                  <button
                    type="button"
                    onClick={() => selectUnderpassSurface(
                      underpasses[(selectedUnderpassIndex - 1 + underpasses.length) % underpasses.length].id,
                    )}
                    aria-label="Select previous underpass in this building"
                  >
                    <ChevronLeft />
                  </button>
                  <div>
                    <span>Underpass {selectedUnderpassIndex + 1} / {underpasses.length}</span>
                    <strong>ID {selectedUnderpass.id}</strong>
                  </div>
                  <button
                    type="button"
                    onClick={() => selectUnderpassSurface(
                      underpasses[(selectedUnderpassIndex + 1) % underpasses.length].id,
                    )}
                    aria-label="Select next underpass in this building"
                  >
                    <ChevronRight />
                  </button>
                </div>
              )}
              {review?.legacyStatus && underpasses.length > 1 && (
                <div className="legacy-review-assignment">
                  <span>
                    Existing <strong>{review.legacyStatus.tag}</strong> status needs an underpass.
                  </span>
                  <button
                    type="button"
                    onClick={() => persistUnderpassStatus(
                      [review.legacyStatus!.tag],
                      { resolveLegacy: true },
                    )}
                    disabled={reviewStatusesDisabled}
                  >
                    Assign to ID {selectedUnderpassId}
                  </button>
                </div>
              )}
              <div className="review-tag-actions">
                {REVIEW_STATUSES.map((status, index) => (
                  <button
                    key={status}
                    type="button"
                    className="review-tag-action"
                    data-tag={status}
                    data-selected={reviewStatus === status}
                    onClick={() => toggleReviewStatus(status)}
                    disabled={reviewStatusesDisabled}
                    aria-pressed={reviewStatus === status}
                  >
                    <kbd>{index + 1}</kbd>
                    <span>{status}</span>
                  </button>
                ))}
                <button
                  type="button"
                  className="review-tag-action"
                  data-tag={HIGHLIGHT_TAG}
                  data-selected={highlightSelected}
                  onClick={toggleHighlight}
                  disabled={tagsDisabled}
                  aria-pressed={highlightSelected}
                >
                  <Star />
                  <span>Highlight</span>
                </button>
              </div>
              <div className="review-tag-state">
                {tagState === "saving" && <span>Saving…</span>}
                {record && tagState !== "loading" && !selectedUnderpass && (
                  <span>Review statuses unavailable: this building has no identified underpass.</span>
                )}
                {selectedUnderpassReview?.automatic && (
                  <span>PointCloud insufficient was selected automatically; you can change or clear it.</span>
                )}
                {tagError && <span role="alert">{tagError}</span>}
              </div>
            </div>
          </div>

          <Tabs defaultValue="layers" className="flex min-h-0 flex-1 flex-col">
            <div className="border-b border-border px-4 py-2">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="layers">Layers</TabsTrigger>
                <TabsTrigger value="attributes">Attributes</TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="layers" className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
              <section className="control-section">
                <div className="control-heading">
                  <span className="flex items-center gap-2"><Box /> Building model</span>
                  <Switch checked={modelVisible} onCheckedChange={setModelVisible} aria-label="Show building model" />
                </div>
                <div className="control-row">
                  <label htmlFor="lod">Level of detail</label>
                  <select id="lod" value={lod ?? ""} onChange={(event) => setLod(event.target.value)} disabled={!record}>
                    {lods.map((value) => <option key={value} value={value}>LoD {value}</option>)}
                  </select>
                </div>
                <div className="control-row">
                  <label htmlFor="outer-ceiling-only">Outer ceilings only</label>
                  <Switch
                    id="outer-ceiling-only"
                    checked={outerCeilingOnly}
                    onCheckedChange={setOuterCeilingOnly}
                    disabled={!record}
                    aria-label="Show only outer ceiling surfaces"
                  />
                </div>
              </section>

              <Separator className="my-4" />

              <section className="control-section">
                <div className="control-heading">
                  <span className="flex items-center gap-2"><Cloud /> COPC point cloud</span>
                  <Switch checked={pointCloudVisible} onCheckedChange={setPointCloudVisible} aria-label="Show point cloud" />
                </div>
                <div className="control-stack">
                  <div className="flex justify-between"><label>Point size</label><span>{pointSize.toFixed(1)} px</span></div>
                  <Slider value={[pointSize]} min={0} max={5} step={0.1} onValueChange={([value]) => setPointSize(value)} />
                </div>
                <div className="control-stack">
                  <div className="flex justify-between"><label>Point budget</label><span>{formatCount(pointBudget)}</span></div>
                  <Slider value={[pointBudget]} min={250_000} max={4_000_000} step={250_000} onValueChange={([value]) => setPointBudget(value)} />
                </div>
              </section>

              <Separator className="my-4" />

              <section>
                <p className="mb-2 text-[11px] font-semibold uppercase text-muted-foreground">Selection</p>
                <LabelRow label="LoD" value={buildingScene?.lod ?? "--"} />
                <LabelRow label="Surfaces" value={buildingScene?.surfaceCount ?? "--"} />
                <LabelRow label="Model vertices" value={buildingScene?.vertexCount ?? "--"} />
                <LabelRow label="Displayed points" value={formatCount(pointStatus.displayedPoints)} />
                <LabelRow label="COPC points" value={formatCount(pointStatus.totalPoints)} />
                <LabelRow
                  label="Point stream"
                  value={
                    !buildingScene
                      ? "--"
                      : pointStatus.loading
                        ? `${Math.round(pointStatus.progress * 100)}%`
                        : "Ready"
                  }
                />
              </section>
            </TabsContent>

            <TabsContent value="attributes" className="min-h-0 flex-1 overflow-y-auto">
              {attributeGroups.length > 0 ? (
                <div className="attribute-groups">
                  {attributeGroups.map((group) => (
                    <section key={group.id} className="attribute-group">
                      <div className="attribute-group-header">
                        <span>{group.type}</span>
                        <span title={group.id}>{group.id}</span>
                      </div>
                      <dl className="attribute-list">
                        {group.attributes.map(([key, value]) => (
                          <div key={key} className="attribute-row">
                            <dt title={key}>{key}</dt>
                            <dd title={formatValue(value)}>{formatValue(value)}</dd>
                          </div>
                        ))}
                      </dl>
                    </section>
                  ))}
                </div>
              ) : (
                <div className="flex h-32 items-center justify-center gap-2 text-xs text-muted-foreground">
                  {loadState === "loading" ? <LoaderCircle className="size-4 animate-spin" /> : <EyeOff className="size-4" />}
                  <span>{loadState === "loading" ? "Loading attributes" : "No attributes"}</span>
                </div>
              )}
            </TabsContent>
          </Tabs>

          <div className="flex items-center justify-between border-t border-border px-4 py-2 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1.5"><Eye className="size-3" /> Direct browser access</span>
            <span className="flex items-center gap-1.5"><Cloud className="size-3" /> COPC</span>
          </div>
        </aside>
      </main>
    </TooltipProvider>
  );
}
