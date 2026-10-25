"""Discoverable request contracts; core validation owns sanitized diagnostics.

The adapter exposes these schemas on object parameters so SDK validation cannot
include arbitrary invalid request values in its error responses.
"""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema

AssetId = Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$')]
Column = Annotated[str, Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,127}$')]
History = Literal['source_rows', 'current', 'historical']


class RequestModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PlanAsset(RequestModel):
    asset_id: AssetId
    scope: dict[Column, Annotated[str, Field(min_length=1, max_length=256)]] = Field(default_factory=dict, max_length=32)
    grain: list[Column] = Field(default=None, min_length=1, max_length=32, json_schema_extra={'uniqueItems': True})
    history: History = None


class ModelPlanRequest(RequestModel):
    intent: str = Field(min_length=1, max_length=2048)
    assets: list[PlanAsset] = Field(min_length=1, max_length=8)


class SemanticAnswer(RequestModel):
    question_code: Literal['functional_dependencies', 'multivalued_dependencies', 'join_dependencies', 'review_principles', 'relationships_unknown', 'grain_key_difference', 'current_row_rule', 'history_rule', 'confirm_relationship']
    answer: str = Field(min_length=1, max_length=2048)
    rationale: str = Field(min_length=1, max_length=4096)
    target_asset: AssetId = None
    columns: list[Column] = Field(default=None, min_length=1, max_length=32)
    target_columns: list[Column] = Field(default=None, min_length=1, max_length=32)


class DecisionRecord(RequestModel):
    id: str = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=1, max_length=4096)
    recorded_by: str = Field(min_length=1, max_length=256)
    recorded_at: str = Field(max_length=64, json_schema_extra={'format': 'date-time'})
    answers: list[SemanticAnswer] = Field(default_factory=list, max_length=16)


class DecisionPlanRequest(ModelPlanRequest):
    assets: list[PlanAsset] = Field(min_length=1, max_length=8,
        json_schema_extra={'prefixItems': [{'required': ['asset_id', 'grain', 'history']}]},
        description='First asset is the anchor and requires explicit grain and history; remaining assets are explicitly selected related context.')


class ModelProposeDecisionRequest(RequestModel):
    plan: DecisionPlanRequest
    record: DecisionRecord
    replace_record_id: str = Field(default=None, min_length=1, max_length=128)


class BusinessRecord(RequestModel):
    id: AssetId
    scope: dict[AssetId, Annotated[str, Field(min_length=1, max_length=256)]] = Field(max_length=32)
    status: Literal['proposed', 'reviewed']
    definition: str = Field(min_length=1, max_length=2048)
    rationale: str = Field(min_length=1, max_length=4096)
    recorded_by: str = Field(min_length=1, max_length=256)
    recorded_at: str = Field(max_length=64, json_schema_extra={'format': 'date-time'})


class ConceptRecord(BusinessRecord):
    name: str = Field(min_length=1, max_length=256)


class RelationshipRecord(BusinessRecord):
    from_: AssetId = Field(alias='from')
    to: AssetId
    predicate: AssetId


class BusinessContextProposeRequest(RequestModel):
    section: Literal['concepts', 'relationships']
    record: ConceptRecord | RelationshipRecord
    replace_record_id: AssetId = None


def inlined_schema(model):
    schema = model.model_json_schema()
    definitions = schema.pop('$defs', {})
    def inline(value):
        if isinstance(value, list):
            return [inline(v) for v in value]
        if isinstance(value, dict):
            if '$ref' in value:
                return inline(definitions[value['$ref'].split('/')[-1]])
            return {k: inline(v) for k, v in value.items() if not (k == 'default' and v is None)}
        return value
    return inline(schema)


PlanInput = Annotated[object, WithJsonSchema(inlined_schema(ModelPlanRequest))]
DecisionInput = Annotated[object, WithJsonSchema(inlined_schema(ModelProposeDecisionRequest))]
BusinessInput = Annotated[object, WithJsonSchema(inlined_schema(BusinessContextProposeRequest))]
