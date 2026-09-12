import pytest

from services.zip_service import ZipError, extract_resumes
from tests.conftest import make_pdf, make_zip


def test_extracts_pdfs_from_nested_dirs_and_skips_junk(tmp_path):
    pdf_a, pdf_b = make_pdf("Alice resume"), make_pdf("Bob resume")
    data = make_zip({
        "batch/alice.pdf": pdf_a,
        "batch/nested/deeper/bob.PDF": pdf_b,
        "__MACOSX/batch/._alice.pdf": b"junk",
        "batch/.DS_Store": b"junk",
        "batch/notes.txt": b"hello",
        "batch/empty.pdf": b"",
    })
    result = extract_resumes(data, str(tmp_path))
    assert result.total_found == 6
    assert [f.candidate_id for f in result.files] == ["CAND-001", "CAND-002"]
    assert {f.filename for f in result.files} == {"batch/alice.pdf", "batch/nested/deeper/bob.PDF"}
    reasons = dict(result.skipped)
    assert reasons["__MACOSX/batch/._alice.pdf"] == "hidden/system file"
    assert reasons["batch/.DS_Store"] == "hidden/system file"
    assert reasons["batch/notes.txt"] == "not a PDF"
    assert reasons["batch/empty.pdf"] == "empty file"
    for f in result.files:
        assert (tmp_path / f"{f.candidate_id}_{f.filename.split('/')[-1]}").exists()


def test_duplicate_files_flagged_by_hash(tmp_path):
    pdf = make_pdf("Same person")
    result = extract_resumes(make_zip({"a.pdf": pdf, "b.pdf": pdf, "c.pdf": make_pdf("Other")}), str(tmp_path))
    assert result.valid_count == 2
    dup = result.duplicates
    assert len(dup) == 1 and dup[0].candidate_id == "CAND-002" and dup[0].duplicate_of == "CAND-001"


def test_empty_zip(tmp_path):
    result = extract_resumes(make_zip({}), str(tmp_path))
    assert result.total_found == 0 and result.valid_count == 0


def test_invalid_zip_raises(tmp_path):
    with pytest.raises(ZipError):
        extract_resumes(b"not a zip at all", str(tmp_path))


def test_zip_slip_member_is_skipped(tmp_path):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.pdf", make_pdf("evil"))
    result = extract_resumes(buf.getvalue(), str(tmp_path))
    assert result.valid_count == 0
    assert result.skipped and result.skipped[0][0] == "../../evil.pdf"
    assert not (tmp_path.parent.parent / "evil.pdf").exists()
    assert not (tmp_path / "evil.pdf").exists()
