from cozypdfs.dir import DIR_SCHEMA_VERSION, Asset, Block, BlockType, Chapter, DIRDocument, DIRMeta


def _sample_document() -> DIRDocument:
    return DIRDocument(
        meta=DIRMeta(title="Pride and Prejudice", author="Jane Austen", language="en"),
        chapters=[
            Chapter(
                id="ch-1",
                title="Chapter 1",
                order=0,
                blocks=[
                    Block(id="ch-1.b0", type=BlockType.HEADING, order=0, content="Chapter 1"),
                    Block(
                        id="ch-1.b1",
                        type=BlockType.PARAGRAPH,
                        order=1,
                        content="It is a truth universally acknowledged...",
                    ),
                    Block(
                        id="ch-1.b2",
                        type=BlockType.TABLE,
                        order=2,
                        content="",
                        confidence=0.2,
                        preserve_as_image=True,
                        asset_id="asset-1",
                    ),
                ],
            )
        ],
        assets=[Asset(id="asset-1", storage_key="books/1/assets/asset-1.png", width=400, height=300)],
    )


def test_default_schema_version_is_current():
    doc = _sample_document()
    assert doc.schema_version == DIR_SCHEMA_VERSION


def test_roundtrips_through_json():
    doc = _sample_document()
    restored = DIRDocument.model_validate_json(doc.model_dump_json())
    assert restored == doc


def test_low_confidence_block_is_flagged_for_preservation():
    doc = _sample_document()
    table_block = doc.chapters[0].blocks[2]
    assert table_block.preserve_as_image is True
    assert table_block.asset_id == "asset-1"
