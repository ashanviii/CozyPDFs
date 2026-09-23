"""Command-line entry point: `python -m cozypdfs convert <pdf> [output.epub]`.

This is a thin wrapper around `ConversionPipeline` for testing the pipeline
directly, ahead of any upload UI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .exceptions import CozyPdfsError
from .pipeline import ConversionPipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cozypdfs", description="Convert a novel PDF into a clean, reflowable EPUB."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    convert_p = subparsers.add_parser("convert", help="Convert a PDF into an EPUB.")
    convert_p.add_argument("pdf", type=Path, help="Path to the source PDF.")
    convert_p.add_argument(
        "output", type=Path, nargs="?", default=None,
        help="Output .epub path (defaults to the PDF's name).",
    )
    convert_p.add_argument("--title", default=None, help="Override the detected title.")
    convert_p.add_argument("--author", default=None, help="Override the detected author.")
    convert_p.add_argument(
        "--debug-dir", type=Path, default=None,
        help="Write a numbered JSON dump of every pipeline stage to this directory.",
    )

    debug_p = subparsers.add_parser(
        "debug", help="Convert a PDF, dumping every stage's output for inspection."
    )
    debug_p.add_argument("pdf", type=Path, help="Path to the source PDF.")
    debug_p.add_argument(
        "outdir", type=Path, nargs="?", default=None,
        help="Directory for the EPUB and debug dumps (defaults to <pdf-name>_debug/).",
    )

    args = parser.parse_args(argv)
    if args.command == "convert":
        return _convert(args.pdf, args.output, args.title, args.author, args.debug_dir)
    if args.command == "debug":
        outdir = args.outdir or args.pdf.with_name(args.pdf.stem + "_debug")
        return _convert(args.pdf, outdir / f"{args.pdf.stem}.epub", None, None, outdir)
    return 1


def _convert(
    pdf_path: Path, output: Path | None, title: str | None, author: str | None,
    debug_dir: Path | None,
) -> int:
    output_path = output or pdf_path.with_suffix(".epub")
    pipeline = ConversionPipeline()

    def on_progress(_stage: str, message: str) -> None:
        print(f"  {message}")

    try:
        result = pipeline.convert(
            pdf_path, output_path, title=title, author=author,
            on_progress=on_progress, debug_dir=debug_dir,
        )
    except CozyPdfsError as exc:
        print(f"Conversion failed: {exc}", file=sys.stderr)
        if debug_dir:
            print(f"Partial debug output (if any): {debug_dir}", file=sys.stderr)
        return 1

    book = result.book
    print()
    print(f"Title:    {book.metadata.title}")
    print(f"Author:   {book.metadata.author or '(unknown)'}")
    print(f"Chapters: {len(book.chapters)}")
    print(f"EPUB:     {result.epub_path}")
    if debug_dir:
        print(f"Debug:    {debug_dir}")
    if result.validation.warnings:
        print("Warnings:")
        for warning in result.validation.warnings:
            print(f"  - {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
