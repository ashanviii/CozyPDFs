import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { ReaderArtifact } from "./types";

export function useReaderArtifact(bookId: string) {
  const [artifact, setArtifact] = useState<ReaderArtifact | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    api
      .getReaderArtifact(bookId)
      .then((data) => {
        if (!cancelled) setArtifact(data);
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [bookId]);

  return { artifact, loading, error };
}
