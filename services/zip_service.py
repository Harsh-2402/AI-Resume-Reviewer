import hashlib
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path, PurePosixPath


class ZipError(Exception):
    pass


@dataclass
class ResumeFile:
    candidate_id: str
    filename: str
    path: str
    sha256: str
    size: int
    duplicate_of: str = ""


@dataclass
class ZipExtractionResult:
    files: list[ResumeFile] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    total_found: int = 0
    extract_dir: str = ""

    @property
    def valid(self) -> list[ResumeFile]:
        return [f for f in self.files if not f.duplicate_of]

    @property
    def duplicates(self) -> list[ResumeFile]:
        return [f for f in self.files if f.duplicate_of]

    @property
    def valid_count(self) -> int:
        return len(self.valid)

    @property
    def summary(self) -> str:
        return (
            f"Total files found: {self.total_found} · Valid resumes: {self.valid_count} · "
            f"Duplicates: {len(self.duplicates)} · Skipped: {len(self.skipped)}"
        )


def candidate_id_for(index: int) -> str:
    return f"CAND-{index:03d}"


def _is_hidden_or_system(parts: tuple[str, ...]) -> bool:
    return any(p.startswith(".") or p == "__MACOSX" for p in parts)


def extract_resumes(zip_bytes: bytes, dest_dir: str) -> ZipExtractionResult:
    """Extract PDF resumes from a ZIP (nested dirs ok). Never raises for a bad member — only for a bad ZIP."""
    result = ZipExtractionResult(extract_dir=dest_dir)
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    try:
        archive = zipfile.ZipFile(BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise ZipError("The uploaded file is not a valid ZIP archive") from exc

    members = [m for m in archive.infolist() if not m.is_dir()]
    members.sort(key=lambda m: m.filename.lower())
    result.total_found = len(members)

    seen_hashes: dict[str, str] = {}
    index = 0
    with archive:
        for member in members:
            name = member.filename
            parts = PurePosixPath(name).parts
            if _is_hidden_or_system(parts):
                result.skipped.append((name, "hidden/system file"))
                continue
            if PurePosixPath(name).suffix.lower() != ".pdf":
                result.skipped.append((name, "not a PDF"))
                continue
            if member.file_size == 0:
                result.skipped.append((name, "empty file"))
                continue

            target = (dest / PurePosixPath(name).name)
            if not str(target.resolve()).startswith(str(dest)):
                result.skipped.append((name, "unsafe path"))
                continue

            try:
                data = archive.read(member)
            except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
                result.skipped.append((name, f"could not read: {str(exc)[:60]}"))
                continue

            index += 1
            cid = candidate_id_for(index)
            target = dest / f"{cid}_{PurePosixPath(name).name}"
            target.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            entry = ResumeFile(
                candidate_id=cid, filename=name, path=str(target), sha256=digest, size=len(data),
            )
            if digest in seen_hashes:
                entry.duplicate_of = seen_hashes[digest]
            else:
                seen_hashes[digest] = cid
            result.files.append(entry)
    return result
