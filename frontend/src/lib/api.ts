/** Thin fetch wrapper for the backend API. All backend access goes through
 * this module — no component should call `fetch` directly. */

import type { ReaderArtifact, ReadingLocator, ReadingProgress } from "../reader/types";

const BASE_URL = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    ...init,
  });
  if (!response.ok) {
    throw new Error((await safeErrorDetail(response)) ?? `${init?.method ?? "GET"} ${path} failed: ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

async function safeErrorDetail(response: Response): Promise<string | null> {
  try {
    const body = await response.json();
    return typeof body?.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}

export interface HealthResponse {
  status: string;
}

export interface MeResponse {
  identity_id: string;
}

export type BookStatus =
  | "uploading"
  | "preparing"
  | "reconstructing"
  | "creating_epub"
  | "ready"
  | "failed";

export interface Book {
  id: string;
  title: string | null;
  author: string | null;
  source_filename: string;
  status: BookStatus;
  page_count: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface UploadResponse {
  book: Book;
  reused: boolean;
}

/** Not proxied through `request` — this is a plain <img src> URL, not a
 * JSON fetch, and must stay a same-origin relative path so the browser
 * attaches the httponly identity cookie automatically. */
export function assetUrl(bookId: string, assetId: string): string {
  return `${BASE_URL}/books/${bookId}/assets/${assetId}`;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  me: () => request<MeResponse>("/me"),

  listBooks: () => request<Book[]>("/books"),
  getBook: (id: string) => request<Book>(`/books/${id}`),
  uploadBook: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<UploadResponse>("/books", { method: "POST", body: formData });
  },
  retryBook: (id: string) => request<Book>(`/books/${id}/retry`, { method: "POST" }),
  deleteBook: (id: string) => request<void>(`/books/${id}`, { method: "DELETE" }),

  getReaderArtifact: (bookId: string) => request<ReaderArtifact>(`/books/${bookId}/reader-artifact`),
  getProgress: (bookId: string) => request<ReadingProgress>(`/books/${bookId}/progress`),
  saveProgress: (bookId: string, locator: ReadingLocator) =>
    request<ReadingProgress>(`/books/${bookId}/progress`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(locator),
    }),
};
