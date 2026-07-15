import { useEffect, useMemo, useRef, useState } from "react";
import {
  Box,
  Building2,
  Cloud,
  ChevronLeft,
  ChevronRight,
  Crosshair,
  Database,
  Eye,
  EyeOff,
  Focus,
  LoaderCircle,
  Search,
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
  type BuildingScene,
} from "@/lib/cityjson-mesh";
import {
  getBuildingObject,
  loadBuildingById,
  normalizeBuildingId,
  type BuildingRecord,
} from "@/lib/fcb";

const FCB_URL = import.meta.env.VITE_FCB_URL ?? "/data/city.fcb";
const COPC_URL = import.meta.env.VITE_COPC_URL ?? "/data/merged.copc";
const UNDERPASS_URL = import.meta.env.VITE_UNDERPASS_URL ?? "/data/underpasses.json";
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

function buildingFromUrl() {
  return new URLSearchParams(window.location.search).get("building") ?? "";
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "Not set";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return VALUE_FORMAT.format(value);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
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
  const [loadState, setLoadState] = useState<LoadState>(initialId ? "loading" : "idle");
  const [error, setError] = useState<string>();
  const [lod, setLod] = useState<string>();
  const [modelVisible, setModelVisible] = useState(true);
  const [outerCeilingOnly, setOuterCeilingOnly] = useState(false);
  const [pointCloudVisible, setPointCloudVisible] = useState(true);
  const [pickEnabled, setPickEnabled] = useState(false);
  const [pickedPoint, setPickedPoint] = useState<PickedWorldPoint>();
  const [pointSize, setPointSize] = useState(1.7);
  const [pointBudget, setPointBudget] = useState(1_500_000);
  const [pointStatus, setPointStatus] = useState<PointCloudStatus>(EMPTY_POINT_STATUS);
  const viewerRef = useRef<SceneViewerHandle>(null);
  const requestRef = useRef(0);

  useEffect(() => {
    const onPopState = () => {
      const id = buildingFromUrl();
      setInputId(id);
      setBuildingId(id);
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

  const attributes = useMemo(() => {
    const buildingObject = record ? getBuildingObject(record) : undefined;
    return Object.entries(buildingObject?.attributes ?? {}).sort(([a], [b]) =>
      a.localeCompare(b),
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
    const url = new URL(window.location.href);
    url.searchParams.set("building", normalized);
    window.history.pushState({}, "", url);
    setInputId(normalized);
    setBuildingId(normalized);
    setPickedPoint(undefined);
  }

  function selectUnderpass(index: number) {
    const id = underpassIds?.[index];
    if (!id) return;
    const url = new URL(window.location.href);
    url.searchParams.set("building", id);
    window.history.replaceState({}, "", url);
    setInputId(id);
    setBuildingId(id);
    setPickedPoint(undefined);
  }

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

          <div className="hidden items-center gap-2 text-xs text-muted-foreground md:flex">
            <span className={`status-dot ${loadState === "error" ? "bg-red-500" : loadState === "ready" ? "bg-emerald-500" : "bg-zinc-400"}`} />
            {loadState === "ready" ? "Building loaded" : loadState === "error" ? "Load failed" : "Ready"}
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
            pickEnabled={pickEnabled}
            pointSize={pointSize}
            pointBudget={pointBudget}
            onPickPoint={setPickedPoint}
            onPointCloudStatus={setPointStatus}
            onError={setError}
          />

          <div className="viewer-toolbar">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant={pickEnabled ? "default" : "secondary"}
                  size="icon"
                  onClick={() => setPickEnabled((enabled) => !enabled)}
                  disabled={!buildingScene}
                  aria-pressed={pickEnabled}
                >
                  <Crosshair />
                  <span className="sr-only">Pick world coordinates</span>
                </Button>
              </TooltipTrigger>
              <TooltipContent>{pickEnabled ? "Stop picking" : "Pick world coordinates"}</TooltipContent>
            </Tooltip>
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
                onClick={() => selectUnderpass(underpassIndex - 1)}
                disabled={loadState === "loading" || underpassIndex <= 0}
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
                onClick={() => selectUnderpass(underpassIndex + 1)}
                disabled={
                  loadState === "loading" ||
                  underpassIds === undefined ||
                  underpassIds.length === 0 ||
                  underpassIndex + 1 >= underpassIds.length
                }
              >
                Next
                <ChevronRight />
              </Button>
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
              {attributes.length > 0 ? (
                <dl className="attribute-list">
                  {attributes.map(([key, value]) => (
                    <div key={key} className="attribute-row">
                      <dt title={key}>{key}</dt>
                      <dd title={formatValue(value)}>{formatValue(value)}</dd>
                    </div>
                  ))}
                </dl>
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
