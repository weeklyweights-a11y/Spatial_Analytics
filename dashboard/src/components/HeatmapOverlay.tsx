import { useEffect, useRef } from "react";
import * as d3 from "d3";
import type { HeatmapSnapshot, ZoneDefinition } from "../types";

interface HeatmapOverlayProps {
  floorPlanUrl: string;
  zones: ZoneDefinition[];
  snapshot: HeatmapSnapshot | null;
  selectedZone: string | null;
  onZoneClick: (name: string) => void;
}

function zoneColor(pct: number): string {
  if (pct <= 0) return "rgba(100, 116, 139, 0.35)";
  if (pct < 30) return "rgba(34, 197, 94, 0.3)";
  if (pct < 60) return "rgba(234, 179, 8, 0.4)";
  if (pct < 85) return "rgba(249, 115, 22, 0.5)";
  return "rgba(239, 68, 68, 0.6)";
}

export function HeatmapOverlay({
  floorPlanUrl,
  zones,
  snapshot,
  selectedZone,
  onZoneClick,
}: HeatmapOverlayProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    container.innerHTML = "";
    const width = 800;
    const height = 600;

    const svg = d3
      .select(container)
      .append("svg")
      .attr("viewBox", `0 0 ${width} ${height}`)
      .attr("width", "100%")
      .style("maxHeight", "520px");

    svg
      .append("image")
      .attr("href", floorPlanUrl)
      .attr("width", width)
      .attr("height", height)
      .attr("preserveAspectRatio", "xMidYMid meet");

    const layer = svg.append("g");

    zones.forEach((zone) => {
      const poly = zone.floor_polygon?.length ? zone.floor_polygon : zone.polygon_coords;
      if (!poly || poly.length < 3) return;
      const occ = snapshot?.zones[zone.name];
      const pct = occ?.pct ?? 0;
      const count = occ?.count ?? 0;
      const points = poly.map((p) => `${p[0]},${p[1]}`).join(" ");
      const cx = poly.reduce((s, p) => s + p[0], 0) / poly.length;
      const cy = poly.reduce((s, p) => s + p[1], 0) / poly.length;

      layer
        .append("polygon")
        .attr("points", points)
        .attr("fill", zoneColor(pct))
        .attr("stroke", selectedZone === zone.name ? "#34d399" : "#64748b")
        .attr("stroke-width", selectedZone === zone.name ? 3 : 1)
        .style("cursor", "pointer")
        .on("click", () => onZoneClick(zone.name))
        .transition()
        .duration(500)
        .attr("fill", zoneColor(pct));

      layer
        .append("text")
        .attr("x", cx)
        .attr("y", cy)
        .attr("text-anchor", "middle")
        .attr("fill", "#e2e8f0")
        .attr("font-size", 12)
        .text(`${zone.name} (${count})`);
    });
  }, [floorPlanUrl, zones, snapshot, selectedZone, onZoneClick]);

  return <div ref={containerRef} className="relative w-full bg-slate-950 rounded-lg border border-slate-800" />;
}
