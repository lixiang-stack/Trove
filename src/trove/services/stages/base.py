from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from trove.content_package import ContentPackage, SourceDocument
from trove.db.models import Item
from trove.ports import StageContext
from trove.services.package_documents import source_document


class StageHandler(Protocol):
    def execute(
        self,
        session: Session,
        item: Item,
        source: SourceDocument,
        context: StageContext,
    ) -> None: ...


def sync_source(package: ContentPackage, item: Item, source: SourceDocument) -> None:
    package.write_source(item.id, source_document(item, base=source))
