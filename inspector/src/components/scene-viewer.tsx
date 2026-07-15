import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react";
import {
  AmbientLight,
  Box3,
  BufferGeometry,
  Color,
  DirectionalLight,
  Float32BufferAttribute,
  Group,
  MathUtils,
  Mesh,
  PerspectiveCamera,
  Points,
  PointsMaterial,
  Raycaster,
  Scene,
  SRGBColorSpace,
  Vector2,
  Vector3,
  WebGLRenderer,
} from "three";
import { ArcballControls } from "three/examples/jsm/controls/ArcballControls.js";
import type { BuildingScene } from "@/lib/cityjson-mesh";
import { setBuildingDisplay } from "@/lib/cityjson-mesh";

// These runtime members are omitted from the Three.js Arcball type declaration.
type ArcballControlsWithFocus = ArcballControls & {
  target: Vector3;
  focus: (point: Vector3, scale: number) => void;
};

const CAMERA_FOV = 45;
const PICK_TOLERANCE_PX = 6;

export interface PointCloudStatus {
  loading: boolean;
  progress: number;
  displayedPoints: number;
  totalPoints?: number;
}

export interface SceneViewerHandle {
  resetCamera: () => void;
}

export interface PickedWorldPoint {
  x: number;
  y: number;
  z: number;
}

interface SceneViewerProps {
  copcUrl: string;
  building?: BuildingScene;
  modelVisible: boolean;
  outerCeilingOnly: boolean;
  pointCloudVisible: boolean;
  pickEnabled: boolean;
  pointSize: number;
  pointBudget: number;
  onPickPoint: (point: PickedWorldPoint) => void;
  onPointCloudStatus: (status: PointCloudStatus) => void;
  onError: (message: string) => void;
}

interface SceneContext {
  scene: Scene;
  camera: PerspectiveCamera;
  renderer: WebGLRenderer;
  controls: ArcballControlsWithFocus;
  render: () => void;
}

type CopcWorkerMessage =
  | { type: "metadata"; totalPoints: number }
  | { type: "progress"; progress: number }
  | { type: "chunk"; positions: Float32Array; colors: Float32Array; pointCount: number; progress: number }
  | { type: "done" }
  | { type: "error"; message: string };

function frameBounds(context: SceneContext, bounds: Box3) {
  const center = bounds.getCenter(new Vector3());
  const size = bounds.getSize(new Vector3());
  const radius = Math.max(size.length() * 0.5, 1);
  const halfVerticalFov = MathUtils.degToRad(CAMERA_FOV * 0.5);
  const halfHorizontalFov = Math.atan(Math.tan(halfVerticalFov) * context.camera.aspect);
  const distance = (radius * 1.18) / Math.sin(Math.min(halfVerticalFov, halfHorizontalFov));
  const viewDirection = new Vector3(0.72, -0.92, 0.62).normalize();
  context.camera.position.copy(center).addScaledVector(viewDirection, distance);
  context.camera.up.set(0, 0, 1);
  context.camera.fov = CAMERA_FOV;
  context.camera.near = Math.max(radius * 0.01, 0.01);
  context.camera.far = radius * 200;
  context.camera.zoom = 1;
  context.camera.updateProjectionMatrix();
  context.controls.target.copy(center);
  context.controls.minDistance = radius * 0.15;
  context.controls.maxDistance = radius * 100;
  context.controls.setCamera(context.camera);
  context.controls.saveState();
  context.render();
}

function centerViewAt(context: SceneContext, point: Vector3) {
  // Arcball's focus transform translates both camera and pivot without rebuilding orientation.
  context.controls.focus(point, 1);
  context.render();
}

function disposePointGroup(group: Group, material: PointsMaterial) {
  group.traverse((object) => {
    if (object instanceof Points) object.geometry.dispose();
  });
  material.dispose();
}

export const SceneViewer = forwardRef<SceneViewerHandle, SceneViewerProps>(
  function SceneViewer(
    {
      copcUrl,
      building,
      modelVisible,
      outerCeilingOnly,
      pointCloudVisible,
      pickEnabled,
      pointSize,
      pointBudget,
      onPickPoint,
      onPointCloudStatus,
      onError,
    },
    ref,
  ) {
    const containerRef = useRef<HTMLDivElement>(null);
    const contextRef = useRef<SceneContext | undefined>(undefined);
    const buildingRef = useRef<BuildingScene | undefined>(undefined);
    const pointsRef = useRef<{ group: Group; material: PointsMaterial } | undefined>(undefined);
    const pointCloudVisibleRef = useRef(pointCloudVisible);
    const pointSizeRef = useRef(pointSize);
    const pickEnabledRef = useRef(pickEnabled);
    const onPickPointRef = useRef(onPickPoint);
    pointCloudVisibleRef.current = pointCloudVisible;
    pointSizeRef.current = pointSize;
    pickEnabledRef.current = pickEnabled;
    onPickPointRef.current = onPickPoint;

    useImperativeHandle(ref, () => ({
      resetCamera() {
        const context = contextRef.current;
        const currentBuilding = buildingRef.current;
        if (context && currentBuilding) frameBounds(context, currentBuilding.localBounds);
      },
    }));

    useEffect(() => {
      const container = containerRef.current;
      if (!container) return;

      const scene = new Scene();
      scene.background = new Color(0xe8ece8);
      const camera = new PerspectiveCamera(CAMERA_FOV, 1, 0.01, 10000);
      camera.up.set(0, 0, 1);
      const renderer = new WebGLRenderer({ antialias: true });
      renderer.outputColorSpace = SRGBColorSpace;
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      container.append(renderer.domElement);

      const controls = new ArcballControls(
        camera,
        renderer.domElement,
        scene,
      ) as ArcballControlsWithFocus;
      controls.enableAnimations = false;
      controls.enableFocus = false;
      controls.cursorZoom = false;
      controls.adjustNearFar = false;
      controls.setGizmosVisible(false);
      scene.add(camera);
      scene.add(new AmbientLight(0xffffff, 0.7));
      const cameraLight = new DirectionalLight(0xffffff, 2.6);
      cameraLight.position.set(-0.8, 1, 1.4);
      cameraLight.target.position.set(0, 0, -1);
      camera.add(cameraLight, cameraLight.target);

      const render = () => renderer.render(scene, camera);
      const context: SceneContext = { scene, camera, renderer, controls, render };
      const onControlsChange = () => render();
      controls.addEventListener("change", onControlsChange);
      const raycaster = new Raycaster();
      const pointer = new Vector2();
      const buildingCenter = new Vector3();
      const viewDirection = new Vector3();
      const intersectionAt = (clientX: number, clientY: number) => {
        const rect = renderer.domElement.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return undefined;
        pointer.set(
          ((clientX - rect.left) / rect.width) * 2 - 1,
          -((clientY - rect.top) / rect.height) * 2 + 1,
        );
        const currentBuilding = buildingRef.current;
        if (currentBuilding) currentBuilding.localBounds.getCenter(buildingCenter);
        else buildingCenter.set(0, 0, 0);
        camera.getWorldDirection(viewDirection);
        const modelDepth = Math.max(
          Math.abs(buildingCenter.sub(camera.position).dot(viewDirection)),
          camera.near,
        );
        const visibleHeight =
          2 * modelDepth * Math.tan(MathUtils.degToRad(camera.getEffectiveFOV() * 0.5));
        raycaster.params.Points.threshold = Math.max(
          (visibleHeight / rect.height) * PICK_TOLERANCE_PX,
          0.01,
        );
        raycaster.setFromCamera(pointer, camera);

        const pickRoots = [buildingRef.current?.group, pointsRef.current?.group].filter(
          (group): group is Group => Boolean(group?.visible),
        );
        return raycaster
          .intersectObjects(pickRoots, true)
          .find(
            ({ object }) =>
              object.visible && (object instanceof Mesh || object instanceof Points),
          );
      };
      const onDoubleClick = (event: MouseEvent) => {
        const intersection = intersectionAt(event.clientX, event.clientY);
        if (intersection) centerViewAt(context, intersection.point);
      };
      let pickStart: { pointerId: number; x: number; y: number } | undefined;
      const onPickPointerDown = (event: PointerEvent) => {
        if (pickEnabledRef.current && event.isPrimary && event.button === 0) {
          pickStart = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
        }
      };
      const onPickPointerUp = (event: PointerEvent) => {
        if (!pickStart || event.pointerId !== pickStart.pointerId) return;
        const movement = Math.hypot(event.clientX - pickStart.x, event.clientY - pickStart.y);
        pickStart = undefined;
        if (!pickEnabledRef.current || movement > 4) return;

        const building = buildingRef.current;
        const intersection = intersectionAt(event.clientX, event.clientY);
        if (!building || !intersection) return;
        onPickPointRef.current({
          x: intersection.point.x + building.origin.x,
          y: intersection.point.y + building.origin.y,
          z: intersection.point.z + building.origin.z,
        });
      };
      const cancelPick = () => {
        pickStart = undefined;
      };
      renderer.domElement.addEventListener("dblclick", onDoubleClick);
      renderer.domElement.addEventListener("pointerdown", onPickPointerDown);
      window.addEventListener("pointerup", onPickPointerUp);
      window.addEventListener("pointercancel", cancelPick);
      const resize = () => {
        const width = Math.max(container.clientWidth, 1);
        const height = Math.max(container.clientHeight, 1);
        renderer.setSize(width, height);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        render();
      };
      const resizeObserver = new ResizeObserver(resize);
      contextRef.current = context;
      resizeObserver.observe(container);
      resize();

      return () => {
        resizeObserver.disconnect();
        renderer.domElement.removeEventListener("dblclick", onDoubleClick);
        renderer.domElement.removeEventListener("pointerdown", onPickPointerDown);
        window.removeEventListener("pointerup", onPickPointerUp);
        window.removeEventListener("pointercancel", cancelPick);
        controls.removeEventListener("change", onControlsChange);
        controls.dispose();
        renderer.dispose();
        contextRef.current = undefined;
        container.replaceChildren();
      };
    }, []);

    useEffect(() => {
      const context = contextRef.current;
      if (!context || !building) return;
      buildingRef.current = building;
      context.scene.add(building.group);
      frameBounds(context, building.localBounds);
      return () => {
        context.scene.remove(building.group);
        if (buildingRef.current === building) buildingRef.current = undefined;
      };
    }, [building]);

    useEffect(() => {
      if (!building) return;
      setBuildingDisplay(building, modelVisible, outerCeilingOnly);
      contextRef.current?.render();
    }, [building, modelVisible, outerCeilingOnly]);

    useEffect(() => {
      const context = contextRef.current;
      if (!context || !building) return;
      const pointOrigin = building.origin;
      const group = new Group();
      group.name = "selected-copc-points";
      group.visible = pointCloudVisibleRef.current;
      const material = new PointsMaterial({
        size: pointSizeRef.current,
        sizeAttenuation: false,
        vertexColors: true,
        transparent: true,
        opacity: 0.92,
      });
      context.scene.add(group);
      pointsRef.current = { group, material };
      let displayedPoints = 0;
      let totalPoints: number | undefined;
      onPointCloudStatus({ loading: true, progress: 0, displayedPoints: 0 });

      const worker = new Worker(new URL("../workers/copc.worker.ts", import.meta.url), { type: "module" });
      worker.onmessage = ({ data }: MessageEvent<CopcWorkerMessage>) => {
        if (data.type === "metadata") {
          totalPoints = data.totalPoints;
          onPointCloudStatus({ loading: true, progress: 0.05, displayedPoints, totalPoints });
        } else if (data.type === "progress") {
          onPointCloudStatus({ loading: true, progress: data.progress, displayedPoints, totalPoints });
        } else if (data.type === "chunk") {
          const geometry = new BufferGeometry();
          geometry.setAttribute("position", new Float32BufferAttribute(data.positions, 3));
          geometry.setAttribute("color", new Float32BufferAttribute(data.colors, 3));
          geometry.computeBoundingSphere();
          group.add(new Points(geometry, material));
          displayedPoints += data.pointCount;
          onPointCloudStatus({ loading: data.progress < 1, progress: data.progress, displayedPoints, totalPoints });
          context.render();
        } else if (data.type === "done") {
          onPointCloudStatus({ loading: false, progress: 1, displayedPoints, totalPoints });
        } else {
          onError(data.message);
        }
      };

      worker.postMessage({
        type: "load",
        url: copcUrl,
        bounds: [building.bounds.min.toArray(), building.bounds.max.toArray()],
        origin: pointOrigin.toArray(),
        pointBudget,
      });

      return () => {
        worker.terminate();
        context.scene.remove(group);
        if (pointsRef.current?.group === group) pointsRef.current = undefined;
        disposePointGroup(group, material);
        if (contextRef.current === context) context.render();
      };
    }, [building, copcUrl, pointBudget, onError, onPointCloudStatus]);

    useEffect(() => {
      const canvas = contextRef.current?.renderer.domElement;
      if (canvas) canvas.style.cursor = pickEnabled ? "crosshair" : "";
    }, [pickEnabled]);

    useEffect(() => {
      const points = pointsRef.current;
      if (!points) return;
      points.group.visible = pointCloudVisible;
      contextRef.current?.render();
    }, [pointCloudVisible]);

    useEffect(() => {
      const points = pointsRef.current;
      if (!points) return;
      points.material.size = pointSize;
      contextRef.current?.render();
    }, [pointSize]);

    return <div ref={containerRef} className="h-full w-full overflow-hidden" />;
  },
);
