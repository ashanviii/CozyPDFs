import { useCallback, useEffect, useState } from "react";
import { api, type Book } from "../lib/api";

const ACTIVE_STATUSES: Book["status"][] = ["uploading", "preparing", "reconstructing", "creating_epub"];

/** Single source of truth for the current owner's library. Centralizes all
 * book API access + optimistic local updates so components never call
 * `api` directly. */
export function useLibrary() {
  const [books, setBooks] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const fetched = await api.listBooks();
      setBooks(fetched);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Books still processing have no push channel yet, so poll lightly until
  // they reach a terminal state (ready/failed) rather than making the user
  // manually refresh to see progress.
  useEffect(() => {
    const hasActiveBook = books.some((book) => ACTIVE_STATUSES.includes(book.status));
    if (!hasActiveBook) return;
    const interval = setInterval(refresh, 4000);
    return () => clearInterval(interval);
  }, [books, refresh]);

  const upload = useCallback(async (file: File) => {
    const { book } = await api.uploadBook(file);
    setBooks((prev) => [book, ...prev.filter((existing) => existing.id !== book.id)]);
    return book;
  }, []);

  const retry = useCallback(async (id: string) => {
    const book = await api.retryBook(id);
    setBooks((prev) => prev.map((existing) => (existing.id === id ? book : existing)));
  }, []);

  const remove = useCallback(async (id: string) => {
    await api.deleteBook(id);
    setBooks((prev) => prev.filter((existing) => existing.id !== id));
  }, []);

  return { books, loading, error, refresh, upload, retry, remove };
}
