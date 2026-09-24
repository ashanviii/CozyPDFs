import { Route, Routes } from "react-router-dom";
import LibraryPage from "./pages/LibraryPage";
import ReaderPage from "./pages/ReaderPage";
import "./App.css";
import "./reader/reader.css";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LibraryPage />} />
      <Route path="/read/:bookId" element={<ReaderPage />} />
    </Routes>
  );
}
