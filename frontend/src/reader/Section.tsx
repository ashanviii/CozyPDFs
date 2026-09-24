import { RenderBlock } from "./RenderBlock";
import type { ReaderSection } from "./types";

const HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"] as const;

interface SectionProps {
  section: ReaderSection;
  bookId: string;
  chapterId: string;
}

/** Renders a section's own heading + blocks, then recurses into child
 * sections — the same tree Phase 2B built by folding DIR's heading levels
 * (reader_artifact/build.py), now walked into real hN elements instead of
 * indentation boxes (that box styling is the devtool preview's concern,
 * not the reader's). */
export function Section({ section, bookId, chapterId }: SectionProps) {
  const HeadingTag = HEADING_TAGS[Math.min(Math.max(section.level, 1), 6) - 1];

  return (
    <section id={section.id} className="reader-section" data-section-id={section.id}>
      {section.title && <HeadingTag className="reader-section__title">{section.title}</HeadingTag>}
      {section.blocks.map((block) => (
        <RenderBlock key={block.id} block={block} bookId={bookId} chapterId={chapterId} />
      ))}
      {section.children.map((child) => (
        <Section key={child.id} section={child} bookId={bookId} chapterId={chapterId} />
      ))}
    </section>
  );
}
