import { BookCard } from "./components/BookCard";
import { Sidebar } from "./components/Sidebar";
import { UploadCard } from "./components/UploadCard";
import { useLibrary } from "./hooks/useLibrary";
import "./App.css";

export default function App() {
  const { books, loading, error, upload, retry, remove } = useLibrary();

  return (
    <div className="app">
      <Sidebar />
      <main className="library">
        <h1>Your Library</h1>
        {error && <p className="library__error">{error}</p>}
        {loading ? (
          <p className="library__loading">Loading your library…</p>
        ) : books.length === 0 ? (
          <div className="library__empty">
            <p>Your library is empty.</p>
            <UploadCard variant="empty" onUpload={upload} />
          </div>
        ) : (
          <div className="library__grid">
            <UploadCard variant="tile" onUpload={upload} />
            {books.map((book) => (
              <BookCard key={book.id} book={book} onRetry={retry} onDelete={remove} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
