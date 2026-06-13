import { useState, useRef, useCallback } from "react";

interface CameraCaptureProps {
  onCapture: (blob: Blob) => void;
}

export function CameraCapture({ onCapture }: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startCamera = useCallback(async () => {
    try {
      const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } });
      setStream(media);
      if (videoRef.current) {
        videoRef.current.srcObject = media;
      }
      setError(null);
    } catch {
      setError("Could not access camera");
    }
  }, []);

  const capture = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (blob) {
        setPreview(canvas.toDataURL("image/jpeg"));
        onCapture(blob);
      }
    }, "image/jpeg", 0.92);
  }, [onCapture]);

  return (
    <div className="space-y-3">
      {!preview ? (
        <div className="relative bg-slate-900 rounded-lg overflow-hidden aspect-video">
          <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" />
        </div>
      ) : (
        <img src={preview} alt="Captured" className="w-full rounded-lg aspect-video object-cover" />
      )}
      {error && <p className="text-red-400 text-sm">{error}</p>}
      <div className="flex gap-2">
        {!stream && (
          <button type="button" onClick={startCamera} className="px-4 py-2 bg-blue-600 rounded-lg text-sm">
            Start Camera
          </button>
        )}
        {stream && !preview && (
          <button type="button" onClick={capture} className="px-4 py-2 bg-emerald-600 rounded-lg text-sm">
            Capture
          </button>
        )}
        {preview && (
          <button
            type="button"
            onClick={() => {
              setPreview(null);
              startCamera();
            }}
            className="px-4 py-2 bg-slate-700 rounded-lg text-sm"
          >
            Retake
          </button>
        )}
      </div>
    </div>
  );
}
