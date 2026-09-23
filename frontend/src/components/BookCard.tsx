import type { Book } from "../lib/api";

const STATUS_LABEL: Record<Book["status"], string> = {
  uploading: "Uploading…",
  preparing: "Preparing…",
  reconstructing: "Reconstructing…",
  creating_epub: "Creating EPUB…",
  ready: "Ready to read",
  failed: "Failed",
};

interface BookCardProps {
  book: Book;
  onRetry: (id: string) => void;
  onDelete: (id: string) => void;
}

export function BookCard({ book, onRetry, onDelete }: BookCardProps) {
  const title = book.title?.trim() || book.source_filename;

  return (
    <div className={`book-card book-card--${book.status}`}>
      <div className="book-card__cover" aria-hidden="true" />
      <p className="book-card__title">{title}</p>
      {book.author && <p className="book-card__author">{book.author}</p>}
      <p className="book-card__status">{STATUS_LABEL[book.status]}</p>
      {book.status === "failed" && book.error_message && (
        <p className="book-card__error">{book.error_message}</p>
      )}
      <div className="book-card__actions">
        {book.status === "failed" && (
          <button type="button" onClick={() => onRetry(book.id)}>
            Retry
          </button>
        )}
        <button type="button" className="book-card__delete" onClick={() => onDelete(book.id)}>
          Delete
        </button>
      </div>
    </div>
  );
}
