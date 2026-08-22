from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOCIAL_APP = ROOT / "frontend" / "mini-app" / "components" / "roxy-social-app.tsx"
REFERENCE_MEMORY = ROOT / "frontend" / "mini-app" / "lib" / "reference-memory.tsx"
MINI_APP_PAGE = ROOT / "frontend" / "mini-app" / "app" / "page.tsx"
UPLOADS = ROOT / "app" / "api" / "v1" / "uploads.py"
REFERENCES = ROOT / "app" / "services" / "references.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_active_mini_app_keeps_saved_library_separate_from_fresh_generation() -> None:
    page = _read(MINI_APP_PAGE)
    social = _read(SOCIAL_APP)
    memory = _read(REFERENCE_MEMORY)

    assert "ReferenceMemoryProvider" in page
    assert "SavedReferencePicker" in social
    assert 'values: { ...(model.ui_schema?.defaults || {}) }' in social
    assert 'kind: "new"' in social
    assert "Добавляются только по нажатию" in memory
    assert "onChange(reference.url)" in memory
    assert "onChange([...selected, reference.url])" in memory

    # A fresh draft is built only from the current model defaults. The reference
    # library is rendered as a picker and is never injected into createDefaultDraft.
    default_draft = social.split("function createDefaultDraft", 1)[1].split(
        "function isEmpty", 1
    )[0]
    assert "SavedReference" not in default_draft
    assert "reference" not in default_draft.lower()


def test_uploaded_media_is_saved_as_hash_deduplicated_reference_memory() -> None:
    uploads = _read(UPLOADS)
    references = _read(REFERENCES)

    assert "hashlib.sha256()" in uploads
    assert "file_hash=file_hash" in uploads
    assert 'source="mini_app_upload"' in uploads
    assert "ReferenceService.register" in uploads

    assert "MAX_PER_KIND = 12" in references
    assert "UserReference.file_hash == file_hash" in references
    assert "touch_urls" in references
    assert "last_used_at" in references
    assert "_prune_kind" in references


def test_saved_reference_picker_respects_model_media_limits() -> None:
    memory = _read(REFERENCE_MEMORY)

    assert "acceptedKinds(field)" in memory
    assert "field.max_items || 20" in memory
    assert "selected.length >= maxItems" in memory
    assert "!selectedSet.has(item.url)" in memory
