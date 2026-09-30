"""GET /api/schema: the tables the app can query, for the schema panel in the UI.

Read once at start-up from the database (as ro_user sees it) and described with
the same hand-written notes the retrieval step uses.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.db.schema import TableInfo
from app.db.schema_docs import PAGILA_TABLES as TABLE_NOTES

router = APIRouter(tags=["schema"])


class SchemaColumn(BaseModel):
    name: str
    type: str
    primary_key: bool
    references: str | None  # "language.language_id" for a foreign key


class SchemaTable(BaseModel):
    name: str
    description: str
    columns: list[SchemaColumn]


class SchemaOut(BaseModel):
    database: str
    tables: list[SchemaTable]


@router.get("/schema")
def schema(request: Request) -> SchemaOut:
    tables: list[TableInfo] = request.app.state.schema_tables
    return SchemaOut(
        database="Pagila",
        tables=[
            SchemaTable(
                name=table.name,
                description=TABLE_NOTES.get(table.name, ""),
                columns=[
                    SchemaColumn(
                        name=c.name,
                        type=c.data_type,
                        primary_key=c.primary_key,
                        references=".".join(c.references) if c.references else None,
                    )
                    for c in table.columns
                ],
            )
            for table in tables
        ],
    )
