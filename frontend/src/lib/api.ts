/** Thin fetch wrapper for the backend API. All backend access goes through
 * this module — no component should call `fetch` directly. */

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
};
