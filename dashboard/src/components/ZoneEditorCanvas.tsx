import { useEffect, useRef, useState } from "react";

interface ZoneEditorCanvasProps {
  imageUrl: string;
  points: number[][];
  onChange: (points: number[][]) => void;
  readOnly?: boolean;
}

export function ZoneEditorCanvas({ imageUrl, points, onChange, readOnly = false }: ZoneEditorCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [localPoints, setLocalPoints] = useState<number[][]>(points);

  useEffect(() => setLocalPoints(points), [points]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);
      if (localPoints.length >= 2) {
        ctx.strokeStyle = "#34d399";
        ctx.fillStyle = "rgba(52, 211, 153, 0.2)";
        ctx.beginPath();
        localPoints.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
        if (localPoints.length >= 3) ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
      localPoints.forEach(([x, y]) => {
        ctx.fillStyle = "#34d399";
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fill();
      });
    };
    img.src = imageUrl;
  }, [imageUrl, localPoints]);

  const handleClick = (ev: React.MouseEvent<HTMLCanvasElement>) => {
    if (readOnly) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = ((ev.clientX - rect.left) / rect.width) * canvas.width;
    const y = ((ev.clientY - rect.top) / rect.height) * canvas.height;
    const next = [...localPoints, [Math.round(x), Math.round(y)]];
    setLocalPoints(next);
    onChange(next);
  };

  const closePolygon = () => {
    if (localPoints.length >= 3) onChange(localPoints);
  };

  return (
    <div>
      <canvas ref={canvasRef} onClick={handleClick} className="max-w-full border border-slate-700 rounded cursor-crosshair" />
      {!readOnly && (
        <div className="flex gap-2 mt-2">
          <button type="button" onClick={closePolygon} className="px-3 py-1 bg-slate-800 rounded text-sm">
            Close polygon
          </button>
          <button
            type="button"
            onClick={() => {
              setLocalPoints([]);
              onChange([]);
            }}
            className="px-3 py-1 bg-slate-800 rounded text-sm"
          >
            Clear
          </button>
        </div>
      )}
    </div>
  );
}
