import { useRef, useState } from "react";

interface UploadCardProps {
  onUpload: (file: File) => Promise<unknown>;
  variant?: "tile" | "empty";
}

/** The one upload affordance in the app — used both as the grid's
 * persistent "Upload PDF" tile and as the empty-library prompt, so there
 * is a single place that owns file-selection/drop/upload behavior. */
export function UploadCard({ onUpload, variant = "tile" }: UploadCardProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setIsUploading(true);
    setError(null);
    try {
      await onUpload(file);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div
      className={`upload-card upload-card--${variant}${isDragging ? " is-dragging" : ""}`}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
      }}
      onDragOver={(event) => {
        event.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setIsDragging(false);
        handleFiles(event.dataTransfer.files);
      }}
      role="button"
      tabIndex={0}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        hidden
        onChange={(event) => handleFiles(event.target.files)}
      />
      {isUploading ? (
        <p className="upload-card__title">Uploading…</p>
      ) : (
        <>
          <p className="upload-card__title">Upload a PDF</p>
          <p className="upload-card__hint">Click or drop a file here</p>
        </>
      )}
      {error && <p className="upload-card__error">{error}</p>}
    </div>
  );
}
