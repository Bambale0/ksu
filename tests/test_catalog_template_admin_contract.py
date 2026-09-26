from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_catalog_template_admin_is_available_from_catalog() -> None:
    source = (ROOT / "frontend/mini-app/components/catalog-trend-folders.tsx").read_text(encoding="utf-8")
    assert 'import { TrendCollectionAdmin } from "@/components/trend-collection-admin"' in source
    assert 'import { TrendCategoryAdmin } from "@/components/trend-category-admin"' in source
    assert 'aria-label="Управление шаблонами и категориями"' in source
    assert '<TrendCollectionAdmin' in source
    assert '<TrendCategoryAdmin' in source


def test_catalog_category_preview_supports_video() -> None:
    source = (ROOT / "frontend/mini-app/components/catalog-trend-folders.tsx").read_text(encoding="utf-8")
    media = (ROOT / "frontend/mini-app/components/trend-preview-media.tsx").read_text(encoding="utf-8")
    assert 'mediaType={folder.preview_media_type}' in source
    assert '<video' in media
    assert 'className={className}' in media
