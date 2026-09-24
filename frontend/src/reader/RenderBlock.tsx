import { assetUrl } from "../lib/api";
import type { ReaderBlock } from "./types";

interface RenderBlockProps {
  block: ReaderBlock;
  bookId: string;
  chapterId: string;
}

/** The one place that maps a ReaderBlockType to real markup — mirrors the
 * same semantic mapping already proven server-side in epub/xhtml.py (real
 * hN/p/ul/table elements, figures with merged captions, footnotes as
 * asides), applied here to JSX instead of an XHTML string. `content` is
 * backend-generated, controlled markup from the reconstruction pipeline
 * (never raw user input), the same trust boundary epub/xhtml.py already
 * relies on to pass it through as-is. */
export function RenderBlock({ block, bookId, chapterId }: RenderBlockProps) {
  const dataAttrs = { "data-block-id": block.id, "data-chapter-id": chapterId };

  if (block.preserve_as_image && block.asset_id) {
    return (
      <figure id={block.id} className="reader-block reader-figure" {...dataAttrs}>
        <img src={assetUrl(bookId, block.asset_id)} alt={block.caption ?? block.type} />
        {block.caption && <figcaption>{block.caption}</figcaption>}
      </figure>
    );
  }

  if (block.type === "footnote") {
    return (
      <aside
        id={block.id}
        className="reader-block reader-footnote"
        {...dataAttrs}
        dangerouslySetInnerHTML={{ __html: block.content }}
      />
    );
  }

  return (
    <div
      id={block.id}
      className={`reader-block reader-block--${block.type}`}
      {...dataAttrs}
      dangerouslySetInnerHTML={{ __html: block.content }}
    />
  );
}
