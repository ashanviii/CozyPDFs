/** Structural sidebar for the Library. Only "All Books" is functional in
 * Phase 1 — there is no reading-progress or folders data yet, so those
 * items are shown but disabled rather than wired to fake behavior. */
export function Sidebar() {
  return (
    <nav className="sidebar">
      <p className="sidebar__section">Library</p>
      <ul className="sidebar__list">
        <li className="is-active">All Books</li>
        <li className="is-disabled" title="Coming soon">
          Currently Reading
        </li>
        <li className="is-disabled" title="Coming soon">
          Finished
        </li>
      </ul>
      <p className="sidebar__section">Folders</p>
      <p className="sidebar__placeholder">Coming soon</p>
    </nav>
  );
}
