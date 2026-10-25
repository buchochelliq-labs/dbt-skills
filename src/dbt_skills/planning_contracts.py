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
        # Keep positional requirements in a separate branch: prefixItems next
        # to items would exempt the anchor from the PlanAsset item schema.
        json_schema_extra={'allOf': [{'prefixItems': [{'required': ['asset_id', 'grain', 'history']}]}]},
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


class RecordsSearchRequest(RequestModel):
    kind: Literal['concepts', 'relationships', 'decisions', 'mappings']
    record_id: str = Field(default=None, min_length=1, max_length=256)
    text: str = Field(default=None, min_length=1, max_length=256)
    scope: dict[AssetId, Annotated[str, Field(min_length=1,max_length=256)]] = Field(default_factory=dict,max_length=32)
    status: Literal['proposed','reviewed'] = None
    offset: int = Field(default=0,ge=0,le=200000)
    limit: int = Field(default=20,ge=1,le=20)


class ResolutionPriority(RequestModel):
    enabled: bool = False
    order: list[AssetId] = Field(default_factory=list,max_length=8)


class ResolutionSettings(RequestModel):
    planning_mode: Literal['conservative','partial'] = 'conservative'
    type_compatibility: Literal['compatible','exact'] = 'compatible'
    provider_priority: ResolutionPriority = Field(default_factory=ResolutionPriority)


class ResolutionPreviewRequest(RequestModel):
    asset_ids: list[AssetId] = Field(min_length=1,max_length=8)
    fields: list[Literal['relation','columns','primary_key','foreign_keys']] = Field(min_length=1,max_length=4)
    settings: ResolutionSettings


class DiffRequest(RequestModel):
    before: str = Field(min_length=32,max_length=32)
    after: str = Field(min_length=32,max_length=32)
    asset_ids: list[AssetId] = Field(default=None,max_length=8)
    record_ids: list[AssetId] = Field(default=None,max_length=32)
    offset: int = Field(default=0,ge=0,le=200000)
    limit: int = Field(default=20,ge=1,le=20)


class LocalUpdatePayload(RequestModel):
    schema_version: Literal[1]
    base: dict[str,str] | None
    proposed_document: dict
    review_diff: str = Field(max_length=1048576)
    proposal_sha256: str = Field(pattern='^[a-f0-9]{64}$')


class UpdateReviewRequest(RequestModel):
    proposal: LocalUpdatePayload
    rebase: bool = False


class MappingRequest(RequestModel):
    id: AssetId
    record_ids: list[AssetId] = Field(min_length=1,max_length=16)
    asset_id: AssetId
    columns: list[Column] = Field(default_factory=list,max_length=32)
    meaning: Literal['represents','representation_equivalence','relationship_evidence']
    scope: dict[Column, Annotated[str,Field(min_length=1,max_length=256)]] = Field(max_length=32)
    rationale: str = Field(min_length=1,max_length=4096)
    recorded_by: str = Field(min_length=1,max_length=256)
    recorded_at: str = Field(max_length=64)
    supporting_evidence: list[Annotated[str,Field(min_length=1,max_length=1024)]] = Field(min_length=1,max_length=16)
    alternatives: list[AssetId] = Field(default_factory=list,max_length=8)
    replace_record_id: AssetId = None


class ImpactRequest(RequestModel):
    asset_ids: list[AssetId] = Field(min_length=1,max_length=8)
    columns: list[Column] = Field(default_factory=list,max_length=32)
    record_ids: list[AssetId] = Field(default_factory=list,max_length=32)
    change: str = Field(min_length=1,max_length=2048)
    offset: int = Field(default=0,ge=0,le=200000)
    limit: int = Field(default=20,ge=1,le=20)


SearchInput = Annotated[object, WithJsonSchema(inlined_schema(RecordsSearchRequest))]
PreviewInput = Annotated[object, WithJsonSchema(inlined_schema(ResolutionPreviewRequest))]
DiffInput = Annotated[object, WithJsonSchema(inlined_schema(DiffRequest))]
ReviewInput = Annotated[object, WithJsonSchema(inlined_schema(UpdateReviewRequest))]
MappingInput = Annotated[object, WithJsonSchema(inlined_schema(MappingRequest))]
ImpactInput = Annotated[object, WithJsonSchema(inlined_schema(ImpactRequest))]


def validate_request(model, value):
    """Discard pydantic's input-bearing diagnostics at the adapter boundary."""
    from .context_limits import check_bounds
    try:
        check_bounds(value)
        # JSON schema advertises contracts; strict runtime validation forbids coercion.
        result = model.model_validate(value, strict=True).model_dump(exclude_none=True)
        if model is UpdateReviewRequest:
            from copy import deepcopy
            result['proposal'] = deepcopy(value['proposal'])
        return result
    except (ValueError, TypeError, RecursionError):
        raise ValueError('Invalid bounded review request') from None
