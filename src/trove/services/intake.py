from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from trove.config import Config
from trove.content_package import ArtifactKind, ContentPackage, sha256_file
from trove.db.models import Artifact, Item
from trove.domain.items import Platform, SourceType
from trove.domain.links import LinkInspection
from trove.domain.urls import (
    canonicalize_epub_url,
    canonicalize_feed_url,
    canonicalize_video_url,
    epub_title_hint,
    podcast_source_key,
)
from trove.errors import ValidationError
from trove.ports import AudioExtractor, BookExtractor, FeedClient
from trove.services.collections import (
    CollectionCreateResult,
    CollectionService,
    collection_block,
)
from trove.services.library import ItemBundle, LibraryService
from trove.services.processing import ProcessingService
from trove.services.uploads import UploadStore, kind_for_suffix


class IntakeService:
    def __init__(
        self,
        config: Config,
        package: ContentPackage,
        library: LibraryService,
        processing: ProcessingService,
        collections: CollectionService,
        feed_client: FeedClient,
        book_extractor: BookExtractor,
        audio_extractor: AudioExtractor,
        uploads: UploadStore,
    ) -> None:
        self.config = config
        self.package = package
        self.library = library
        self.processing = processing
        self.collections = collections
        self.feed_client = feed_client
        self.book_extractor = book_extractor
        self.audio_extractor = audio_extractor
        self.uploads = uploads

    # ------------------------------------------------------------------
    # Video URLs
    # ------------------------------------------------------------------
    def add_video_url(self, raw_url: str) -> tuple[ItemBundle, bool]:
        canonical = canonicalize_video_url(raw_url)
        bundle, deduplicated = self.library.create_item(
            source_key=canonical.source_key,
            source_type=SourceType.VIDEO_URL,
            platform=canonical.platform,
            title=canonical.canonical,
            source_url_raw=canonical.raw,
            source_url_canonical=canonical.canonical,
        )
        if not deduplicated:
            self.processing.create_run(bundle.item.id)
            return self.library.get(bundle.item.id), False
        return bundle, True

    # ------------------------------------------------------------------
    # EPUB URL
    # ------------------------------------------------------------------
    def add_epub_url(
        self, raw_url: str, *, canonical_url: str | None = None
    ) -> tuple[ItemBundle, bool]:
        canonical = canonicalize_epub_url(canonical_url or raw_url)
        existing = self._find_by_source_key(canonical)
        if existing is not None:
            return existing, True
        bundle, deduplicated = self.library.create_item(
            source_key=canonical,
            source_type=SourceType.EPUB_URL,
            platform=Platform.WEB,
            title=epub_title_hint(canonical),
            source_url_raw=raw_url,
            source_url_canonical=canonical,
        )
        if deduplicated:
            return bundle, True
        self.processing.create_run(bundle.item.id)
        return self.library.get(bundle.item.id), False

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------
    def add_collection(self, inspection: LinkInspection) -> CollectionCreateResult:
        if inspection.kind.value != "collection":
            raise ValidationError(
                "Link is not a collection", details={"code": "collection.empty"}
            )
        collection, _ = self.collections.create_or_update(
            source_key=inspection.canonical_url,
            source_url_raw=inspection.raw_url,
            source_url_canonical=inspection.canonical_url,
            platform=str(inspection.platform),
            title=inspection.title,
            author=inspection.author,
            episode_count=inspection.episode_count,
            total_duration_sec=inspection.total_duration_sec,
        )
        added = 0
        attached = 0
        skipped = 0
        runs = 0
        warnings: list[dict[str, object]] = list(inspection.warnings)
        for episode in inspection.episodes:
            existing = self.library.find_by_source_key(episode.source_key)
            if existing is not None:
                if existing.item.collection_id not in {None, collection.id}:
                    skipped += 1
                    continue
                self.collections.attach_item(collection, existing, episode.index)
                attached += 1
                continue
            block = collection_block(collection, episode.index)
            bundle, deduplicated = self.library.create_item(
                source_key=episode.source_key,
                source_type=SourceType.VIDEO_URL,
                platform=collection.platform,
                title=episode.title,
                source_url_raw=episode.canonical_url,
                source_url_canonical=episode.canonical_url,
                author=collection.author,
                duration_sec=episode.duration_sec,
                collection_id=collection.id,
                collection_index=episode.index,
                extra_source={"collection": block},
            )
            if deduplicated:
                if bundle.item.collection_id != collection.id:
                    self.collections.attach_item(collection, bundle, episode.index)
                attached += 1
                continue
            added += 1
            runs += 1
            self.processing.create_run(bundle.item.id)
        refreshed = self.collections.refresh_counts(collection.id)
        return CollectionCreateResult(
            collection=refreshed,
            added_count=added,
            attached_count=attached,
            skipped_count=skipped,
            run_count=runs,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Local paths
    # ------------------------------------------------------------------
    def add_host_path(self, raw_path: str) -> tuple[ItemBundle, bool]:
        if not raw_path or not raw_path.strip():
            raise ValidationError("File path cannot be empty", details={"code": "path.empty"})
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            raise ValidationError("Enter an absolute path", details={"code": "path.relative"})
        try:
            path = path.resolve(strict=True)
        except (OSError, FileNotFoundError) as exc:
            raise ValidationError("File not found", details={"code": "path.not_found"}) from exc
        if not path.is_file():
            raise ValidationError("Path is not a file", details={"code": "path.not_file"})
        if not path.stat().st_mode & 0o444:
            raise ValidationError("File is not readable", details={"code": "path.not_readable"})
        kind = kind_for_suffix(path.suffix.lower())
        if kind is None:
            raise ValidationError("Unsupported file type", details={"code": "upload.invalid_type"})
        checksum = sha256_file(path)
        return self._add_local_file(
            kind=kind,
            source_path=path,
            checksum=checksum,
            title=path.stem,
            uploaded=False,
        )

    def add_upload(self, upload_id: str) -> tuple[ItemBundle, bool]:
        record = self.uploads.load(upload_id)
        path = Path(record.path)
        try:
            bundle = self._add_local_file(
                kind=record.kind,
                source_path=path,
                checksum=record.sha256,
                title=Path(record.filename).stem,
                uploaded=True,
                size=record.size,
                validated=True,
            )
        except Exception:
            self.uploads.cleanup(upload_id)
            raise
        if bundle[1] or record.kind == "epub":
            # Duplicates need no source; EPUB is copied into the package during intake.
            self.uploads.cleanup(upload_id)
        return bundle

    def _add_local_file(
        self,
        *,
        kind: str,
        source_path: Path,
        checksum: str,
        title: str,
        uploaded: bool,
        size: int | None = None,
        validated: bool = False,
    ) -> tuple[ItemBundle, bool]:
        source_type = {
            "audio": SourceType.LOCAL_AUDIO,
            "video": SourceType.LOCAL_VIDEO,
            "epub": SourceType.EPUB,
        }[kind]
        if not validated:
            if kind == "epub":
                self.book_extractor.validate(source_path)
            else:
                self.audio_extractor.probe(source_path, kind=kind)
        existing = self._find_by_source_key(checksum)
        if existing is not None:
            return existing, True
        if kind == "epub" and size is not None and size > self.config.max_epub_bytes:
            raise ValidationError(
                "EPUB exceeds the size limit", details={"code": "upload.too_large"}
            )
        bundle, deduplicated = self.library.create_item(
            source_key=checksum,
            source_type=source_type,
            platform=Platform.LOCAL,
            title=title,
            source_path=(
                None if uploaded and kind == "epub" else str(source_path)
            ),
            extra_source={"uploaded": uploaded},
        )
        if deduplicated:
            return bundle, True
        if kind == "epub":
            self._copy_book(bundle.item.id, source_path)
        self.processing.create_run(bundle.item.id)
        return self.library.get(bundle.item.id), False

    def _copy_book(self, item_id: str, source: Path) -> None:
        installed = self.package.copy_artifact(
            item_id,
            ArtifactKind.BOOK,
            source,
            mime="application/epub+zip",
        )
        with self.library.sessions() as session:
            session.add(
                Artifact(
                    item_id=item_id,
                    kind=installed.kind,
                    path=installed.relative_path,
                    sha256=installed.sha256,
                    size=installed.size,
                    mime=installed.mime,
                )
            )
            session.commit()

    def _find_by_source_key(self, source_key: str) -> ItemBundle | None:
        with self.library.sessions() as session:
            item = session.execute(
                select(Item).where(
                    Item.source_key == source_key,
                    Item.deleted_at.is_(None),
                )
            ).scalars().first()
            if item is None:
                return None
            from trove.services.library import item_bundle

            return item_bundle(session, item)

    # ------------------------------------------------------------------
    # Podcast
    # ------------------------------------------------------------------
    def preview_feed(self, feed_url: str):
        canonical = canonicalize_feed_url(feed_url)
        return self.feed_client.preview(canonical)

    def add_podcast_episode(
        self,
        feed_url: str,
        episode_guid: str | None = None,
        enclosure_url: str | None = None,
    ) -> tuple[ItemBundle, bool]:
        canonical_feed = canonicalize_feed_url(feed_url)
        preview = self.feed_client.preview(canonical_feed)
        episode = next(
            (
                entry
                for entry in preview.episodes
                if (episode_guid and entry.guid == episode_guid)
                or (
                    not episode_guid
                    and enclosure_url
                    and entry.enclosure_url == enclosure_url
                )
            ),
            None,
        )
        if episode is None:
            raise ValidationError(
                "Episode not found in feed", details={"code": "feed.episode_not_found"}
            )
        source_key = podcast_source_key(canonical_feed, episode.guid, episode.enclosure_url)
        bundle, deduplicated = self.library.create_item(
            source_key=source_key,
            source_type=SourceType.PODCAST_EPISODE,
            platform=Platform.PODCAST,
            title=episode.title,
            source_url_raw=canonical_feed,
            source_url_canonical=canonical_feed,
            author=episode.author or preview.author,
            published_at=episode.published_at,
            duration_sec=episode.duration_sec,
            extra_source={
                "feed": {
                    "url": canonical_feed,
                    "episode_guid": episode.guid,
                    "enclosure_url": episode.enclosure_url,
                    "enclosure_type": episode.enclosure_type,
                    "enclosure_size": episode.enclosure_size,
                }
            },
        )
        if deduplicated:
            return bundle, True
        self.processing.create_run(bundle.item.id)
        return self.library.get(bundle.item.id), False
