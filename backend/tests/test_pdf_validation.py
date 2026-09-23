import pytest

from cozypdfs.domain import pdf_validation
from tests.factories import make_pdf_bytes


def test_has_pdf_magic_bytes_true_for_real_pdf():
    assert pdf_validation.has_pdf_magic_bytes(make_pdf_bytes())


def test_has_pdf_magic_bytes_false_for_plain_text():
    assert not pdf_validation.has_pdf_magic_bytes(b"just some plain text, not a pdf")


def test_extract_pdf_info_reads_page_count_and_metadata():
    data = make_pdf_bytes(pages=3, title="My Book", author="Jane Doe")

    info = pdf_validation.extract_pdf_info(data)

    assert info.page_count == 3
    assert info.title == "My Book"
    assert info.author == "Jane Doe"


def test_extract_pdf_info_omits_blank_metadata():
    data = make_pdf_bytes(pages=1)

    info = pdf_validation.extract_pdf_info(data)

    assert info.title is None
    assert info.author is None


def test_extract_pdf_info_rejects_corrupt_data_with_magic_bytes():
    with pytest.raises(pdf_validation.InvalidPDFError):
        pdf_validation.extract_pdf_info(b"%PDF-1.4 this is not really a valid pdf body")


def test_extract_pdf_info_rejects_plain_text():
    with pytest.raises(pdf_validation.InvalidPDFError):
        pdf_validation.extract_pdf_info(b"just some plain text, not a pdf")
