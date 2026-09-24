import { useParams } from "react-router-dom";
import { ReaderView } from "../reader/ReaderView";

export default function ReaderPage() {
  const { bookId } = useParams<{ bookId: string }>();
  if (!bookId) return null;
  return <ReaderView bookId={bookId} />;
}
