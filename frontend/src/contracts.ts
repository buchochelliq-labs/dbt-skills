export type Reader = "steward" | "restricted";
export type Approval = "Approved" | "Draft" | "Needs review";
export type Outcome = "permitted" | "denied" | "unsupported" | "unknown";
export interface Domain {
  id: string;
  name: string;
  parent: string | null;
  description: string;
  owner: string | null;
  technicalOwner: string | null;
  steward?: string | null;
  providerPolicy?: string | null;
  ttl: number | null;
  icon?: string;
}
export interface Knowledge {
  id: string;
  name: string;
  type: string;
  domain: string;
  memberships: string[];
  summary: string;
  definition: string;
  scope: string;
  grain: string;
  status: Approval;
  origin: string;
  version: number;
  owner: string;
  source: string;
  sourcePath: string;
  effective: string;
  validFrom: string;
  validTo?: string;
  synonyms: string[];
  related: string[];
  originId: string;
  formula?: string;
  unit?: string;
  aggregation?: string;
  dimensions?: string[];
  logic?: string;
  exclusions?: string;
  ttl?: number;
  hidden?: boolean;
  restricted?: boolean;
  history: KnowledgeRevision[];
}
export interface KnowledgeRevision {
  revision: number;
  definition: string;
  status: Approval;
  origin: string;
  changedAt: number;
}
export interface ScopedDefinition {
  knowledgeId: string;
  revision: number;
  scope: string;
  grain: string;
  timeInterpretation: string;
  inclusions: string;
  exclusions: string;
}
export interface Provider {
  retired?: boolean;
  id: string;
  name: string;
  kind: "uc" | "openmetadata" | "authored";
  enabled: boolean;
  ttl: number;
  health: "healthy" | "outage" | "denied" | "malformed";
  scope: string[];
  workspace: string;
  metastore: string;
  capabilities: Record<string, Outcome>;
}
export interface SourceField {
  path: string;
  type: string;
  nullable: boolean;
  comment: string;
  classification: string;
  key: string;
}
export interface SourceAsset {
  id: string;
  nativeId: string;
  providerId: string;
  name: string;
  type: "catalog" | "schema" | "table" | "view" | "metric_view";
  parent: string | null;
  owner: string;
  description: string;
  tags: Record<string, string>;
  fields: SourceField[];
  domainIds: string[];
  knowledgeIds: string[];
  observedAt: number;
  sourceRevision: string;
  sourceEvidence?: {
    relation: CatalogSourceEvidence;
    columns?: CatalogSourceEvidence;
  };
  hidden?: boolean;
  restricted?: boolean;
  discloseExistence?: boolean;
}
export interface CatalogSourceEvidence {
  provider: string;
  asset_id: string;
  native_id: string;
  document: string;
  locator: string;
  revision: string;
  scope: string;
  source_at: string | null;
  retrieved_at: string;
  verified_at: string | null;
  evidence_type: "declaration";
  derivation: never[];
}
export interface Relationship {
  id: string;
  source: string;
  target: string;
  type:
    | "membership"
    | "is_a"
    | "part_of"
    | "business"
    | "mapping"
    | "join"
    | "lineage"
    | "dependency";
  label: string;
  scope: string;
  cardinality: string;
  provenance: string;
  approval: Approval;
  sourceField?: string;
  targetField?: string;
}
export interface Mapping {
  id: string;
  knowledgeId: string;
  attribute: string;
  assetId: string;
  fieldPath: string;
  type: string;
  scope: string;
  validFrom: string;
  validTo?: string;
  evidence: string;
  status: Approval;
}
export interface FactEvidence {
  originId: string;
  originRevision: number;
  providerId: string;
  assetId: string;
  fieldPath?: string;
  sourcePath: string;
  observedAt: number;
  sourceRevision: string;
  validFrom: string;
  validTo?: string;
  approval: Approval;
  origin: string;
  reader: Reader;
  policyVersion: number;
  replica: boolean;
  confidence: "declared";
  authority: "not assessed";
}
export interface Fact {
  id: string;
  value: string;
  evidence: FactEvidence;
}
export interface CacheEntry {
  key: string;
  knowledgeId: string;
  fact: Fact;
  retrievedAt: number;
  expiresAt: number;
  configVersion: number;
  reader: Reader;
  scope: string;
}
export interface CacheObservation {
  knowledgeId: string;
  factId: string;
  providerId: string;
  at: number;
  hit: boolean;
}
export interface ResolutionRequest {
  question: string;
  objectId?: string;
  scope: string;
  reader: Reader;
}
export interface ResolutionOutcome {
  schema_version: 1;
  simulation: boolean;
  state:
    | "sufficient"
    | "ambiguous"
    | "missing"
    | "withheld"
    | "scopeMismatch"
    | "denied"
    | "incomplete"
    | "error";
  message: string;
  facts: Fact[];
  trace: string[];
  choices?: { id: string; name: string; scope: string }[];
}
export type PublicationState =
  | "Draft"
  | "Reviewed"
  | "Conflict"
  | "Unsupported"
  | "Failed"
  | "Saved"
  | "Verified"
  | "Mismatch"
  | "Exported";
export interface Proposal {
  id: string;
  originId: string;
  originRevision: number;
  targetId: string;
  field: string;
  before: unknown;
  after: unknown;
  expectedRevision: number;
  reason: string;
  audience: string;
  state: PublicationState;
  dependencies: string[];
  evidence: string;
  nativeBaseFingerprint?: string;
  nativeResult?: Record<string, any>;
  reviewedAt?: number;
  reviewDecision?: string;
}
export interface TargetObservation {
  nativeObservation?: Record<string, any>;
  id: string;
  name: string;
  kind: string;
  providerId: string;
  revision: number;
  content: Record<string, any>;
  capability: Outcome;
  permission: Outcome;
  audience: string;
  atomic: boolean;
  failNext: boolean;
  mismatchNext: boolean;
  origins: Record<string, { originId: string; revision: number }>;
}
export interface DeliveryAttempt {
  id: string;
  proposalId: string;
  at: number;
  state: PublicationState;
  acknowledged: boolean;
  readback: "matches" | "mismatch" | "unknown";
  indexing: "unknown";
  answerUse: "unknown";
  message: string;
}
export interface PageRecord {
  id: string;
  name: string;
  domain: string;
  owner: string;
  synonyms: string[];
  summary: string;
  body: string;
  relatedAssets: string[];
  sources: string[];
  state: "Draft" | "Published" | "Archived";
}
export interface State {
  domains: Domain[];
  knowledge: Knowledge[];
  providers: Provider[];
  assets: SourceAsset[];
  relationships: Relationship[];
  mappings: Mapping[];
  cache: CacheEntry[];
  observations: CacheObservation[];
  proposals: Proposal[];
  targets: TargetObservation[];
  deliveries: DeliveryAttempt[];
  pages: PageRecord[];
  clock: number;
  policyVersion: number;
  configVersion: number;
  sequence: number;
  ttlDismissed: boolean;
}
export interface MetadataAdapter {
  read(
    state: State,
    provider: Provider,
    object: Knowledge,
    fact: string,
    reader: Reader,
  ):
    | { status: "sufficient"; fact: Fact }
    | {
        status: "missing" | "unavailable" | "unsupported" | "denied" | "error";
      };
}
export interface PublicationAdapter {
  readTarget(id: string): TargetObservation | undefined;
  conditionalSave(
    id: string,
    revision: number,
    field: string,
    value: unknown,
  ): TargetObservation;
}
