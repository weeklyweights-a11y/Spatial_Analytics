import { useEffect, useRef, useState } from "react";
import { useWebSocket } from "../hooks/useWebSocket";
import type { TrackingMessage, TrackingPerson } from "../types";

interface CameraFeedProps {
  cameraId: string;
  cameraName: string;
  onPersonClick: (participantId: string, x: number, y: number) => void;
}

export function CameraFeed({ cameraId, cameraName, onPersonClick }: CameraFeedProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [displaySize, setDisplaySize] = useState({ w: 320, h: 180 });
  const { lastMessage } = useWebSocket<TrackingMessage>(`/ws/tracking/${cameraId}`, true);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setDisplaySize({ w: el.clientWidth, h: el.clientHeight });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const persons = lastMessage?.persons ?? [];

  const scaleBox = (p: TrackingPerson) => {
    const fw = p.frame_width || displaySize.w;
    const fh = p.frame_height || displaySize.h;
    const sx = displaySize.w / fw;
    const sy = displaySize.h / fh;
    const [x1, y1, x2, y2] = p.bbox;
    return {
      left: x1 * sx,
      top: y1 * sy,
      width: (x2 - x1) * sx,
      height: (y2 - y1) * sy,
    };
  };

  return (
    <div className="bg-slate-900 rounded-lg overflow-hidden border border-slate-800">
      <div className="px-2 py-1 text-xs text-slate-400 flex justify-between">
        <span>{cameraName}</span>
        <span>{persons.filter((p) => p.participant_id).length} tracked</span>
      </div>
      <div ref={containerRef} className="relative w-full aspect-video bg-black">
        <img
          src={`/api/v1/stream/${cameraId}`}
          alt={cameraName}
          className="w-full h-full object-contain"
        />
        {persons.map((p) => {
          if (!p.participant_id) return null;
          const box = scaleBox(p);
          return (
            <button
              key={p.track_id}
              type="button"
              aria-label={p.name}
              className="absolute border-2 border-transparent hover:border-emerald-400/80 cursor-pointer"
              style={{
                left: box.left,
                top: box.top,
                width: box.width,
                height: box.height,
              }}
              onClick={(e) => {
                e.stopPropagation();
                onPersonClick(p.participant_id!, e.clientX, e.clientY);
              }}
            />
          );
        })}
      </div>
    </div>
  );
}
