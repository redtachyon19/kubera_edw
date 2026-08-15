import { useEffect, useMemo, useRef, useState } from 'react';

import LAND from './land.json';
import './Globe.css';

/**
 * One place on the globe. Anything without a value is drawn as a bare fix.
 *
 * `id` rather than `iso3` because this layer is no longer only countries: the
 * trade desk draws ports and chokepoints through it, which have their own
 * identifiers. Callers that plot countries still pass an ISO3 and get it back.
 */
export interface GlobePoint {
  id: string;
  name: string;
  lat: number;
  lon: number;
  /** Drives colour and radius. Null means the metric has no reading here. */
  value: number | null;
  /** What the readout prints when this point is under the cursor. */
  detail: string;
}

/**
 * A system drawn on top of the countries — a tropical cyclone, not a reading.
 *
 * Marks are their own layer because they are not a value at a country: they sit
 * at sea, they move, and their size means wind speed rather than position on a
 * ramp. Feeding them through `points` would have put a storm in the country
 * table and coloured it as if it were an economic metric.
 */
export interface GlobeMark {
  id: string;
  /** Which glyph is drawn. The silhouettes are what tell the two apart. */
  kind: 'cyclone' | 'fire';
  lat: number;
  lon: number;
  label: string;
  detail: string;
  /**
   * 0–1, how large the glyph draws: Saffir-Simpson category for a cyclone,
   * burned area for a fire. One number because the globe should not have to
   * know what either scale means.
   */
  weight: number;
  /** Degrees clockwise from north. Cyclones only; null for anything static. */
  heading: number | null;
}

/**
 * A trade flow drawn as an arc between two places.
 *
 * Its own layer for the same reason marks are: a ribbon is not a value *at* a
 * country, it is a relationship *between* two, and it has two endpoints where
 * every other thing on this globe has one.
 */
export interface GlobeRibbon {
  id: string;
  fromLat: number;
  fromLon: number;
  toLat: number;
  toLon: number;
  /** 0–1. Drives stroke width — the whole point of a ribbon is comparative bulk. */
  weight: number;
  /**
   * Goods colour, or null when the flow is too mixed for one to be honest.
   * Null draws neutral rather than picking the nominal winner.
   */
  colour: string | null;
  label: string;
  detail: string;
}

/** Which two colours the ramp runs between. */
export interface GlobePalette {
  low: string;
  high: string;
}

/** Gains green, losses red — what every desk but the weather one wants. */
const DIRECTION: GlobePalette = { low: 'var(--down)', high: 'var(--up)' };

interface Props {
  points: GlobePoint[];
  /** The value that sits at the middle of the colour ramp. */
  midpoint: number;
  /** Distance from the midpoint that saturates the ramp. */
  spread: number;
  /** True when a high value is a good thing, which decides which end is which. */
  higherIsBetter: boolean;
  selected: string | null;
  onSelect: (id: string | null) => void;
  /** Printed under the readout, e.g. "CPI inflation, 2025". */
  caption: string;
  /**
   * Ramp colours. Defaults to gains/losses; weather overrides it, because a
   * cold capital is not a loss and 30°C is not a rally.
   */
  palette?: GlobePalette;
  /** Systems drawn over the countries. */
  marks?: GlobeMark[];
  /** Trade flows drawn as arcs above the surface. */
  ribbons?: GlobeRibbon[];
  /** Which ribbon is pinned, if any. */
  selectedRibbon?: string | null;
  onSelectRibbon?: (id: string | null) => void;
  /** Idle text under the readout, when nothing is hovered or pinned. */
  hint?: string;
}

const SIZE = 720;
const R = SIZE / 2 - 18;
const CENTRE = SIZE / 2;
const RAD = Math.PI / 180;

/** Coastlines as `[lon, lat]` rings — Natural Earth 110m, simplified. */
type Ring = [number, number][];

// No segment of a coastline may span more than this before it is subdivided.
// Two things need it: a long segment is a straight line in lon/lat, which is not
// a straight line on a sphere, and — worse — a segment whose ends are both on
// the near face can still pass behind the globe in between, which would draw a
// chord straight across the visible disc.
const MAX_STEP = 4;

/**
 * Subdivide a ring so no segment exceeds `MAX_STEP`, once, at module load.
 *
 * Longitudes are deliberately left **unwrapped** — a ring crossing the
 * antimeridian continues past 180 rather than jumping to −180. `project` takes
 * a sine and a cosine of it, so it does not care, and it keeps every segment
 * local, which is what the horizon bisection below relies on.
 */
function densify(ring: Ring): Ring {
  const out: Ring = [];
  let carry = 0;

  for (let i = 0; i < ring.length; i += 1) {
    const [rawLon, lat] = ring[i];
    const lon = rawLon + carry;

    if (i === 0) {
      out.push([lon, lat]);
      continue;
    }

    const [previousLon, previousLat] = out[out.length - 1];
    // A jump wider than half the world is the seam, not travel.
    let target = lon;
    if (target - previousLon > 180) {
      carry -= 360;
      target -= 360;
    } else if (previousLon - target > 180) {
      carry += 360;
      target += 360;
    }

    const steps = Math.ceil(
      Math.max(Math.abs(target - previousLon), Math.abs(lat - previousLat)) / MAX_STEP,
    );
    for (let s = 1; s <= steps; s += 1) {
      const t = s / steps;
      out.push([
        previousLon + (target - previousLon) * t,
        previousLat + (lat - previousLat) * t,
      ]);
    }
  }
  return out;
}

const COASTS: Ring[] = (LAND as Ring[]).map(densify);

// Spin slowly while nobody is looking at it, and stop the moment a cursor
// arrives — not only once it is dragged. An unattended globe that never moves
// reads as a picture, but one that keeps turning under the pointer drags its
// targets out from under the click, and a ribbon you were about to open sails
// away mid-reach. It resumes from wherever it was left as soon as the cursor
// goes.
const IDLE_SPIN = 0.055;
const DRAG_SCALE = 0.32;
const MAX_TILT = 78;

type Rotation = { lon: number; lat: number };

/** Orthographic projection: the hemisphere facing the reader, nothing behind it. */
function project(lat: number, lon: number, rotation: Rotation) {
  const phi = lat * RAD;
  const lambda = (lon + rotation.lon) * RAD;
  const phi0 = rotation.lat * RAD;

  const cosPhi = Math.cos(phi);
  const x = cosPhi * Math.sin(lambda);
  const y = Math.cos(phi0) * Math.sin(phi) - Math.sin(phi0) * cosPhi * Math.cos(lambda);
  // The z component is the only thing that says whether a point is on the near
  // face or the far one. Everything else about the two is identical.
  const z = Math.sin(phi0) * Math.sin(phi) + Math.cos(phi0) * cosPhi * Math.cos(lambda);

  return { x: CENTRE + x * R, y: CENTRE - y * R, z };
}

/**
 * The same projection for a point held `altitude` above the surface.
 *
 * Ribbons are flown above the globe rather than painted onto it. An arc lying on
 * the sphere would be fighting the coastlines for the same pixels and would
 * disappear the instant it crossed a marker; lifted, it reads as a flight over
 * the surface, which is also what it depicts.
 *
 * That lift changes what "hidden" means. A surface point is hidden whenever it
 * faces away, but a raised point behind the horizon can still be visible over
 * the top of the globe — which is exactly how a long route should look as it
 * goes round the back. The occlusion test is therefore the real one: the point
 * is blocked only if it is behind the centre plane *and* its projected position
 * falls inside the disc of the sphere.
 */
function projectAloft(lat: number, lon: number, rotation: Rotation, altitude: number) {
  const phi = lat * RAD;
  const lambda = (lon + rotation.lon) * RAD;
  const phi0 = rotation.lat * RAD;

  const cosPhi = Math.cos(phi);
  const ux = cosPhi * Math.sin(lambda);
  const uy = Math.cos(phi0) * Math.sin(phi) - Math.sin(phi0) * cosPhi * Math.cos(lambda);
  const uz = Math.sin(phi0) * Math.sin(phi) + Math.cos(phi0) * cosPhi * Math.cos(lambda);

  const radius = 1 + altitude;
  const x = ux * radius;
  const y = uy * radius;
  const z = uz * radius;

  return {
    x: CENTRE + x * R,
    y: CENTRE - y * R,
    z,
    hidden: z < 0 && Math.sqrt(x * x + y * y) < 1,
  };
}

// ── Great circles ────────────────────────────────────────────────────────────

/** Geographic lat/lon to a unit vector in the earth-fixed frame. */
function toVector(lat: number, lon: number): [number, number, number] {
  const phi = lat * RAD;
  const lambda = lon * RAD;
  const cosPhi = Math.cos(phi);
  return [cosPhi * Math.cos(lambda), cosPhi * Math.sin(lambda), Math.sin(phi)];
}

/**
 * The great-circle path between two points, as `[lat, lon]` samples.
 *
 * Spherical linear interpolation, so the result is the actual shortest path over
 * the sphere rather than a straight line in lat/lon — which on any route with
 * real east-west extent is a visibly different and wrong curve, and which would
 * also cross the antimeridian as a seam.
 *
 * Sampling is proportional to the arc's length: a short hop needs a handful of
 * points and a trans-Pacific run needs many, and spending the same on both is
 * either coarse at one end or wasteful at the other. These are computed in the
 * earth-fixed frame, so they do not change as the globe turns and are built once
 * per ribbon rather than once per frame.
 */
function greatCircle(
  fromLat: number,
  fromLon: number,
  toLat: number,
  toLon: number,
): { points: [number, number][]; span: number } {
  const a = toVector(fromLat, fromLon);
  const b = toVector(toLat, toLon);

  const dot = Math.max(-1, Math.min(1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]));
  const omega = Math.acos(dot);

  // Coincident endpoints — a port trading with its own country's centroid, or a
  // rounding collision. There is no arc to draw.
  if (omega < 1e-6) return { points: [], span: 0 };

  const steps = Math.max(12, Math.min(96, Math.round((omega / Math.PI) * 96)));
  const sinOmega = Math.sin(omega);
  const points: [number, number][] = [];

  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps;
    const wa = Math.sin((1 - t) * omega) / sinOmega;
    const wb = Math.sin(t * omega) / sinOmega;

    const x = a[0] * wa + b[0] * wb;
    const y = a[1] * wa + b[1] * wb;
    const z = a[2] * wa + b[2] * wb;

    points.push([Math.asin(Math.max(-1, Math.min(1, z))) / RAD, Math.atan2(y, x) / RAD]);
  }

  return { points, span: omega };
}

// How high a ribbon flies at its apex, as a fraction of the globe's radius. A
// long route arcs higher than a short one — which is both how the eye expects
// distance to read and what keeps a busy region from becoming a stack of
// identical arcs at the same height.
const RIBBON_LIFT = 0.055;
const RIBBON_LIFT_MAX = 0.3;

/** A meridian or parallel, clipped to the visible face. */
function arc(
  rotation: Rotation,
  fixed: number,
  isMeridian: boolean,
  step = 4,
): string {
  const path: string[] = [];
  let drawing = false;

  const from = isMeridian ? -90 : -180;
  const to = isMeridian ? 90 : 180;

  for (let t = from; t <= to; t += step) {
    const { x, y, z } = isMeridian
      ? project(t, fixed, rotation)
      : project(fixed, t, rotation);
    if (z < 0) {
      drawing = false;
      continue;
    }
    path.push(`${drawing ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`);
    drawing = true;
  }
  return path.join('');
}

/**
 * The point where the segment `visible`–`hidden` crosses the horizon.
 *
 * Found by bisection rather than algebra: it reuses `project` as the test, so
 * the clip can never disagree with the projection it is clipping. Eight rounds
 * on a segment of at most four degrees settles well inside a pixel.
 */
function horizon(visible: [number, number], hidden: [number, number], rotation: Rotation) {
  let near = visible;
  let far = hidden;
  for (let i = 0; i < 8; i += 1) {
    const mid: [number, number] = [(near[0] + far[0]) / 2, (near[1] + far[1]) / 2];
    if (project(mid[1], mid[0], rotation).z >= 0) near = mid;
    else far = mid;
  }
  return project(near[1], near[0], rotation);
}

/**
 * Every coastline on the near face, as one path.
 *
 * Stroked, not filled. A filled landmass would have to be closed along the limb
 * wherever a continent runs off the edge, and it would put a slab of tone on a
 * page whose whole idea is hairlines. An engraved outline is both easier to get
 * right and the thing that actually belongs here.
 */
function coastlines(rotation: Rotation): string {
  const parts: string[] = [];

  for (const ring of COASTS) {
    let drawing = false;
    let previous: [number, number] | null = null;

    for (const point of ring) {
      const projected = project(point[1], point[0], rotation);

      if (projected.z >= 0) {
        if (!drawing && previous) {
          // Coming over the horizon: start at the crossing, not at the first
          // vertex that happens to be visible, or the coast stops short of the
          // limb and the globe looks peeled.
          const edge = horizon(point, previous, rotation);
          parts.push(`M${edge.x.toFixed(1)} ${edge.y.toFixed(1)}`);
          parts.push(`L${projected.x.toFixed(1)} ${projected.y.toFixed(1)}`);
        } else {
          parts.push(`${drawing ? 'L' : 'M'}${projected.x.toFixed(1)} ${projected.y.toFixed(1)}`);
        }
        drawing = true;
      } else {
        if (drawing && previous) {
          const edge = horizon(previous, point, rotation);
          parts.push(`L${edge.x.toFixed(1)} ${edge.y.toFixed(1)}`);
        }
        drawing = false;
      }

      previous = point;
    }
  }

  return parts.join('');
}

/**
 * Signed position on the ramp, −1 to 1.
 *
 * `higherIsBetter` is what stops the colours lying: a high return is good and a
 * high inflation rate is not, and the same ramp has to be able to say both.
 */
function ramp(value: number, midpoint: number, spread: number, higherIsBetter: boolean) {
  const t = Math.max(-1, Math.min(1, (value - midpoint) / (spread || 1)));
  return higherIsBetter ? t : -t;
}

/**
 * A point `distance` degrees along the great circle from (lat, lon) at `bearing`.
 *
 * The heading arrow is drawn between this point and the storm rather than at a
 * screen-space angle, because north is not up on a rotated globe — an arrow
 * drawn at `heading` degrees from vertical would point somewhere else entirely
 * the moment the reader spins or tilts it.
 */
function advance(lat: number, lon: number, bearing: number, distance: number) {
  const d = distance * RAD;
  const theta = bearing * RAD;
  const phi = lat * RAD;
  const lambda = lon * RAD;

  const sinPhi2 = Math.sin(phi) * Math.cos(d) + Math.cos(phi) * Math.sin(d) * Math.cos(theta);
  const phi2 = Math.asin(Math.max(-1, Math.min(1, sinPhi2)));
  const lambda2 =
    lambda +
    Math.atan2(
      Math.sin(theta) * Math.sin(d) * Math.cos(phi),
      Math.cos(d) - Math.sin(phi) * sinPhi2,
    );

  return { lat: phi2 / RAD, lon: lambda2 / RAD };
}

/**
 * The cyclone glyph: an eye and two arms, which is the symbol every weather map
 * uses and the only one a reader recognises at this size.
 *
 * One arm is drawn here and the second is the same path turned half a turn by
 * the caller — a pair is what reads as rotation, where a single hook reads as a
 * comma and four arms read as a flower.
 */
function arm(radius: number): string {
  const r = radius;
  return [
    `M0 0`,
    `C${(r * 0.2).toFixed(1)} ${(-r * 0.55).toFixed(1)},`,
    `${(r * 0.72).toFixed(1)} ${(-r * 0.92).toFixed(1)},`,
    `${r.toFixed(1)} ${(-r * 0.3).toFixed(1)}`,
    `C${(r * 0.68).toFixed(1)} ${(-r * 0.42).toFixed(1)},`,
    `${(r * 0.34).toFixed(1)} ${(-r * 0.26).toFixed(1)},`,
    `0 0`,
    'Z',
  ].join(' ');
}

/**
 * The flame glyph: a leaf with a drawn-out tip, filled.
 *
 * A fire is told from a cyclone by silhouette, not by colour. On a globe whose
 * temperature layer is already a blue-to-red ramp, "an orange thing" is not a
 * signal — a shape is.
 */
function flame(radius: number): string {
  const r = radius;
  return [
    `M0 ${(-r).toFixed(1)}`,
    `C${(r * 0.64).toFixed(1)} ${(-r * 0.4).toFixed(1)},`,
    `${(r * 0.6).toFixed(1)} ${(r * 0.36).toFixed(1)},`,
    `0 ${(r * 0.76).toFixed(1)}`,
    `C${(-r * 0.6).toFixed(1)} ${(r * 0.36).toFixed(1)},`,
    `${(-r * 0.64).toFixed(1)} ${(-r * 0.4).toFixed(1)},`,
    `0 ${(-r).toFixed(1)}`,
    'Z',
  ].join(' ');
}

export default function Globe({
  points,
  midpoint,
  spread,
  higherIsBetter,
  selected,
  onSelect,
  caption,
  palette = DIRECTION,
  marks,
  ribbons,
  selectedRibbon = null,
  onSelectRibbon,
  hint = 'Drag to rotate · click a country to pin it',
}: Props) {
  const [rotation, setRotation] = useState<Rotation>({ lon: -10, lat: 18 });
  const [hovered, setHovered] = useState<string | null>(null);
  const [hoveredMark, setHoveredMark] = useState<string | null>(null);
  const [hoveredRibbon, setHoveredRibbon] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [pointerOver, setPointerOver] = useState(false);
  const frame = useRef<number>(0);
  const last = useRef<{ x: number; y: number } | null>(null);
  const moved = useRef(false);

  // The idle spin runs off requestAnimationFrame rather than a CSS animation so
  // it shares a clock with the projection — the markers and the graticule have
  // to move as one thing.
  useEffect(() => {
    if (dragging || pointerOver) return undefined;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return undefined;
    let previous = performance.now();
    const tick = (now: number) => {
      const elapsed = now - previous;
      previous = now;
      setRotation((r) => ({ ...r, lon: (r.lon - IDLE_SPIN * elapsed * 0.06) % 360 }));
      frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [dragging, pointerOver]);

  function onPointerDown(event: React.PointerEvent<SVGSVGElement>) {
    (event.target as Element).setPointerCapture?.(event.pointerId);
    last.current = { x: event.clientX, y: event.clientY };
    moved.current = false;
    setDragging(true);
  }

  function onPointerMove(event: React.PointerEvent<SVGSVGElement>) {
    if (!last.current) return;
    const dx = event.clientX - last.current.x;
    const dy = event.clientY - last.current.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) moved.current = true;
    last.current = { x: event.clientX, y: event.clientY };
    setRotation((r) => ({
      lon: r.lon + dx * DRAG_SCALE,
      // Clamped short of the poles: at 90° the projection degenerates and the
      // graticule collapses into a line.
      lat: Math.max(-MAX_TILT, Math.min(MAX_TILT, r.lat + dy * DRAG_SCALE)),
    }));
  }

  function onPointerUp() {
    last.current = null;
    setDragging(false);
  }

  const projected = useMemo(
    () =>
      points
        .map((point) => ({ point, ...project(point.lat, point.lon, rotation) }))
        // Painter's algorithm: the far face is culled, and what is left is drawn
        // back to front so nearer markers sit on top.
        .filter((p) => p.z > 0)
        .sort((a, b) => a.z - b.z),
    [points, rotation],
  );

  // Storms are projected on the same clock as the countries, so a spin moves the
  // whole scene as one object rather than sliding the systems over the map.
  const systems = useMemo(
    () =>
      (marks ?? [])
        .map((mark) => {
          const at = project(mark.lat, mark.lon, rotation);
          const ahead =
            mark.heading === null ? null : advance(mark.lat, mark.lon, mark.heading, 6);
          return { mark, ...at, tip: ahead ? project(ahead.lat, ahead.lon, rotation) : null };
        })
        .filter((m) => m.z > 0)
        .sort((a, b) => a.z - b.z),
    [marks, rotation],
  );

  // The arcs themselves, in earth-fixed coordinates. Deliberately keyed on
  // `ribbons` alone and NOT on rotation: the spin runs at 60fps and re-slerping
  // three hundred arcs on every frame is the one thing here that would actually
  // drop frames. Only the projection below is per-frame, and that is arithmetic.
  const arcs = useMemo(
    () =>
      (ribbons ?? [])
        .map((ribbon) => {
          const { points: path, span } = greatCircle(
            ribbon.fromLat,
            ribbon.fromLon,
            ribbon.toLat,
            ribbon.toLon,
          );
          return {
            ribbon,
            path,
            // Apex height scales with how far the route actually goes.
            lift: Math.min(RIBBON_LIFT_MAX, RIBBON_LIFT + (span / Math.PI) * 0.16),
          };
        })
        .filter((arc) => arc.path.length > 1),
    [ribbons],
  );

  const drawnRibbons = useMemo(
    () =>
      arcs
        .map(({ ribbon, path, lift }) => {
          const segments: string[] = [];
          let current: string[] = [];
          let depth = -1;

          path.forEach(([lat, lon], index) => {
            // Zero at both ends and highest in the middle, so a ribbon leaves
            // and meets the surface at its ports instead of hovering over them.
            const altitude = lift * Math.sin((index / (path.length - 1)) * Math.PI);
            const at = projectAloft(lat, lon, rotation, altitude);

            if (at.hidden) {
              // Behind the globe. Close the run rather than drawing a chord
              // straight through the planet to wherever it re-emerges.
              if (current.length > 1) segments.push(current.join(''));
              current = [];
              return;
            }

            depth = Math.max(depth, at.z);
            current.push(
              `${current.length ? 'L' : 'M'}${at.x.toFixed(1)} ${at.y.toFixed(1)}`,
            );
          });
          if (current.length > 1) segments.push(current.join(''));

          return { ribbon, d: segments.join(' '), depth };
        })
        .filter((arc) => arc.d)
        // Painter's algorithm again: arcs nearer the reader are drawn last so a
        // route over the Atlantic sits above one round the far side.
        .sort((a, b) => a.depth - b.depth),
    [arcs, rotation],
  );

  const meridians = useMemo(
    () => [-150, -120, -90, -60, -30, 0, 30, 60, 90, 120, 150, 180].map((lon) => arc(rotation, lon, true)),
    [rotation],
  );
  const parallels = useMemo(
    () => [-60, -30, 0, 30, 60].map((lat) => arc(rotation, lat, false)),
    [rotation],
  );
  const coasts = useMemo(() => coastlines(rotation), [rotation]);

  const active = hovered ?? selected;
  const readout = active ? points.find((p) => p.id === active) ?? null : null;
  // A storm sits on top of the countries, so it wins the readout too — pointing
  // at a hurricane and being told the weather in the country behind it would be
  // the wrong answer to an unambiguous question.
  const markReadout = hoveredMark ? (marks ?? []).find((m) => m.id === hoveredMark) ?? null : null;
  // A ribbon under the cursor is the most specific thing there — it is drawn
  // over the ocean where nothing else competes, so pointing at one is always
  // deliberate.
  const activeRibbon = hoveredRibbon ?? selectedRibbon;
  const ribbonReadout = activeRibbon
    ? (ribbons ?? []).find((r) => r.id === activeRibbon) ?? null
    : null;

  return (
    <div className={`globe${dragging ? ' is-dragging' : ''}`}>
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="globe__svg"
        role="img"
        aria-label="Rotatable globe of world markets"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        // `pointerenter`/`pointerleave` rather than `over`/`out`: the latter
        // pair fires again on every crossing between the globe's own children,
        // so moving from a ribbon to a marker would read as leaving and the
        // spin would stutter back on mid-gesture.
        onPointerEnter={() => setPointerOver(true)}
        onPointerLeave={() => {
          setPointerOver(false);
          onPointerUp();
        }}
      >
        <defs>
          <radialGradient id="globe-face" cx="34%" cy="30%" r="78%">
            <stop offset="0%" stopColor="var(--globe-face-lit)" />
            <stop offset="100%" stopColor="var(--globe-face-dim)" />
          </radialGradient>
        </defs>

        <circle cx={CENTRE} cy={CENTRE} r={R} className="globe__ocean" fill="url(#globe-face)" />

        <g className="globe__grid">
          {parallels.map((d, i) => (
            <path key={`p${i}`} d={d} />
          ))}
          {meridians.map((d, i) => (
            <path key={`m${i}`} d={d} />
          ))}
        </g>

        {/* Over the graticule so the coast reads as the subject and the grid as
            the paper it is drawn on, and under the markers, which are the data. */}
        <path className="globe__coast" d={coasts} />

        <circle cx={CENTRE} cy={CENTRE} r={R} className="globe__limb" />

        {/* Under the port markers: the ribbon is the relationship, the marker is
            the place, and a place should never be buried under its own traffic. */}
        <g className="globe__ribbons">
          {drawnRibbons.map(({ ribbon, d }) => {
            const isActive = ribbon.id === (hoveredRibbon ?? selectedRibbon);
            const width = 0.6 + Math.max(0, Math.min(1, ribbon.weight)) * 5.2;

            return (
              <g
                key={ribbon.id}
                className={`globe__ribbon${isActive ? ' is-active' : ''}${
                  ribbon.colour ? '' : ' is-mixed'
                }`}
              >
                {/* A 1px stroke is almost impossible to hit with a pointer. This
                    invisible copy is what the cursor actually catches. */}
                <path
                  className="globe__ribbon-hit"
                  d={d}
                  strokeWidth={Math.max(9, width + 8)}
                  onPointerEnter={() => setHoveredRibbon(ribbon.id)}
                  onPointerLeave={() =>
                    setHoveredRibbon((current) => (current === ribbon.id ? null : current))
                  }
                  onClick={() => {
                    if (moved.current || !onSelectRibbon) return;
                    onSelectRibbon(selectedRibbon === ribbon.id ? null : ribbon.id);
                  }}
                />
                <path
                  className="globe__ribbon-line"
                  d={d}
                  strokeWidth={isActive ? width + 1.4 : width}
                  style={ribbon.colour ? { stroke: ribbon.colour } : undefined}
                />
              </g>
            );
          })}
        </g>

        <g className="globe__points">
          {projected.map(({ point, x, y, z }) => {
            const has = point.value !== null;
            const t = has ? ramp(point.value as number, midpoint, spread, higherIsBetter) : 0;
            // Markers near the limb are seen at a glancing angle and are dimmed
            // to sell the curvature; z is already the cosine of that angle.
            const depth = 0.5 + 0.5 * z;
            const radius = (has ? 5.5 + Math.abs(t) * 5 : 3) * (0.72 + 0.28 * z);
            const isActive = point.id === active;

            return (
              <circle
                key={point.id}
                cx={x}
                cy={y}
                r={isActive ? radius + 3 : radius}
                className={`globe__dot${has ? '' : ' is-empty'}${isActive ? ' is-active' : ''}`}
                style={{
                  fill: has
                    ? t >= 0
                      ? `color-mix(in oklab, ${palette.high} ${Math.round(28 + t * 72)}%, var(--globe-neutral))`
                      : `color-mix(in oklab, ${palette.low} ${Math.round(28 - t * 72)}%, var(--globe-neutral))`
                    : 'var(--globe-neutral)',
                  opacity: depth,
                }}
                onPointerEnter={() => setHovered(point.id)}
                onPointerLeave={() => setHovered((h) => (h === point.id ? null : h))}
                onClick={() => {
                  // A drag that ends over a marker is not a click on it.
                  if (!moved.current) onSelect(selected === point.id ? null : point.id);
                }}
              />
            );
          })}
        </g>

        {/* Above the countries: a storm is over the map, not a property of it. */}
        <g className="globe__marks">
          {systems.map(({ mark, x, y, z, tip }) => {
            const depth = 0.55 + 0.45 * z;
            // Weight is the whole point of the size: a category 5 has to be
            // obviously larger than a tropical storm. The floor matters as much
            // as the ceiling — a country dot reaches ~10, so anything under that
            // makes a named event the least visible thing on its own layer.
            const radius = (11 + Math.max(0, Math.min(1, mark.weight)) * 13) * (0.72 + 0.28 * z);
            const isActive = mark.id === hoveredMark;
            const fire = mark.kind === 'fire';

            return (
              <g
                key={mark.id}
                className={`globe__storm${fire ? ' is-fire' : ''}${isActive ? ' is-active' : ''}`}
                style={{ opacity: depth }}
                onPointerEnter={() => setHoveredMark(mark.id)}
                onPointerLeave={() => setHoveredMark((h) => (h === mark.id ? null : h))}
              >
                {/* Drawn first so the glyph covers the root of its own arrow. */}
                {tip && tip.z > 0 && (
                  <line
                    className="globe__storm-heading"
                    x1={x}
                    y1={y}
                    x2={tip.x}
                    y2={tip.y}
                  />
                )}
                <g transform={`translate(${x.toFixed(1)} ${y.toFixed(1)})`}>
                  {fire ? (
                    <>
                      <path className="globe__fire-body" d={flame(radius)} />
                      {/* The hot core is what stops a small flame reading as a
                          plain teardrop at the size a distant fire draws. */}
                      <path className="globe__fire-core" d={flame(radius * 0.46)} />
                    </>
                  ) : (
                    <>
                      <path className="globe__storm-arm" d={arm(radius)} />
                      <path className="globe__storm-arm" d={arm(radius)} transform="rotate(180)" />
                      <circle className="globe__storm-eye" r={Math.max(1.4, radius * 0.15)} />
                    </>
                  )}
                </g>
                {/* The glyphs are thin and have holes; this is what the pointer
                    actually has to hit for the readout to be usable. */}
                <circle className="globe__storm-hit" cx={x} cy={y} r={radius * 1.15} />
              </g>
            );
          })}
        </g>
      </svg>

      <div className="globe__readout" aria-live="polite">
        {ribbonReadout ? (
          <>
            <span className="globe__readout-name">{ribbonReadout.label}</span>
            <span className="globe__readout-value">{ribbonReadout.detail}</span>
          </>
        ) : markReadout ? (
          <>
            <span className="globe__readout-name">{markReadout.label}</span>
            <span className="globe__readout-value">{markReadout.detail}</span>
          </>
        ) : readout ? (
          <>
            <span className="globe__readout-name">{readout.name}</span>
            <span className="globe__readout-value">{readout.detail}</span>
          </>
        ) : (
          <span className="globe__readout-idle">{hint}</span>
        )}
        <span className="globe__readout-caption">{caption}</span>
      </div>
    </div>
  );
}
