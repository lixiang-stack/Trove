from __future__ import annotations

from sqlalchemy.orm import Session

from trove.content_package import SourceDocument
from trove.db.models import Item
from trove.ports import SearchIndex, StageContext


class IndexStage:
    def __init__(self, search_index: SearchIndex) -> None:
        self.search_index = search_index

    def execute(
        self,
        session: Session,
        item: Item,
        source: SourceDocument,
        context: StageContext,
    ) -> None:
        self.search_index.index_item(item.id)
