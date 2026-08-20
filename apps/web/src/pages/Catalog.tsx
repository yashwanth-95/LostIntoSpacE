import { Navigate } from 'react-router-dom';

/**
 * Catalog.
 *
 * The audit flagged Explore and Catalog as two screens over one data model, and
 * the brief is explicit that they must not duplicate it. Rather than ship a
 * second grid over the same `/space-objects` endpoint, Catalog redirects into
 * Explore, which already provides the category filtering, search, sorting and
 * detail views a catalogue needs.
 *
 * Kept as a route so the nav entry and any existing links resolve rather than
 * 404. If the two genuinely diverge later — a dense table view against a visual
 * browser, say — this is where that would live.
 */
export default function Catalog() {
  return <Navigate to="/explore" replace />;
}
