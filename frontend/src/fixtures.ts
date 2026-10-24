import { initialDomains, initialKnowledge } from "./data.js";
import type {
  State,
  SourceAsset,
  Knowledge,
  Provider,
  Relationship,
} from "./contracts";
export const START = Date.UTC(2026, 9, 23, 9);
const capabilities = {
  discovery: "permitted",
  inspection: "permitted",
  data: "denied",
  modification: "permitted",
  management: "unknown",
} as const;
export function seed(): State {
  const providers: Provider[] = [
    {
      id: "uc-customer",
      name: "Unity Catalog — Customer",
      kind: "uc",
      enabled: true,
      ttl: 24,
      health: "healthy",
      scope: [
        "customer",
        "operations",
        "service",
        "lifecycle",
        "retention",
        "onboarding",
      ],
      workspace: "azure-customer-dev",
      metastore: "ms-customer",
      capabilities: { ...capabilities },
    },
    {
      id: "uc-finance",
      name: "Unity Catalog — Finance",
      kind: "uc",
      enabled: true,
      ttl: 24,
      health: "healthy",
      scope: ["finance", "revenue", "collections"],
      workspace: "azure-finance-dev",
      metastore: "ms-finance",
      capabilities: { ...capabilities },
    },
    {
      id: "openmetadata",
      name: "OpenMetadata",
      kind: "openmetadata",
      enabled: true,
      ttl: 12,
      health: "outage",
      scope: ["*"],
      workspace: "Metadata service",
      metastore: "om-demo",
      capabilities: { ...capabilities, modification: "unsupported" },
    },
    {
      id: "authored",
      name: "Authored YAML and Markdown",
      kind: "authored",
      enabled: true,
      ttl: 24,
      health: "healthy",
      scope: ["*"],
      workspace: "Local repository",
      metastore: "authored",
      capabilities: { ...capabilities, management: "unsupported" },
    },
  ];
  const knowledge: Knowledge[] = initialKnowledge.map((k: any) => ({
    ...k,
    memberships: k.id === "active-customer" ? ["service"] : [],
    validFrom: "2026-10-01",
    originId: k.originId || `uol:${k.id}`,
    history: [],
    restricted: ["mrr", "billing-active", "overdue"].includes(k.id),
  }));
  knowledge.push(
    ...[
      {
        id: "individual",
        name: "Individual customer",
        type: "Concept",
        domain: "customer",
        definition:
          "A natural person participating in a customer relationship.",
        related: ["customer-entity"],
        grain: "Person",
      },
      {
        id: "contract",
        name: "Contract",
        type: "Concept",
        domain: "customer",
        definition: "A commercial agreement consisting of contract lines.",
        related: ["contract-line"],
        grain: "Contract",
      },
      {
        id: "contract-line",
        name: "Contract line",
        type: "Concept",
        domain: "customer",
        definition:
          "A separately specified service obligation within a contract.",
        related: ["contract"],
        grain: "Contract line",
      },
      {
        id: "private-concept",
        name: "Confidential acquisition cohort",
        type: "Concept",
        domain: "finance",
        definition: "Hidden synthetic metadata sentinel.",
        related: [],
        grain: "Cohort",
        hidden: true,
      },
    ].map((k) => ({
      ...k,
      summary: k.definition,
      memberships: [],
      scope: "Enterprise",
      status: "Approved" as const,
      origin: "Curated",
      version: 1,
      owner: "Data Office",
      source: "Authored definitions",
      sourcePath: `concepts/${k.id}.yaml`,
      effective: "1 Oct 2026",
      validFrom: "2026-10-01",
      synonyms: [],
      originId: `uol:${k.id}`,
      history: [],
    })),
  );
  const assets: SourceAsset[] = [];
  const add = (
    id: string,
    name: string,
    type: SourceAsset["type"],
    parent: string | null,
    providerId = "uc-customer",
    extra: Partial<SourceAsset> = {},
  ) =>
    assets.push({
      id,
      nativeId: `native-${id}`,
      providerId,
      name,
      type,
      parent,
      owner:
        providerId === "uc-finance"
          ? "Finance Engineering"
          : "Customer Platform",
      description: `Governed ${type.replace("_", " ")} metadata for ${name}.`,
      tags: { domain: providerId === "uc-finance" ? "Finance" : "Customer" },
      fields: [],
      domainIds: [providerId === "uc-finance" ? "finance" : "customer"],
      knowledgeIds: [],
      observedAt: START - 2 * 3600000,
      sourceRevision: "native-r1",
      ...extra,
    });
  add("customer-catalog", "customer", "catalog", null);
  add("customer-core", "customer.core", "schema", "customer-catalog");
  add("customer-metrics", "customer.metrics", "schema", "customer-catalog");
  add(
    "customers",
    "customer.core.customers",
    "table",
    "customer-core",
    "uc-customer",
    {
      knowledgeIds: ["customer-entity"],
      fields: [
        {
          path: "customer_id",
          type: "BIGINT",
          nullable: false,
          comment: "Canonical customer identifier.",
          classification: "Internal identifier",
          key: "Declared primary key; enforcement unknown",
        },
        {
          path: "region",
          type: "STRING",
          nullable: true,
          comment: "Reporting region.",
          classification: "Internal",
          key: "None",
        },
        {
          path: "status",
          type: "STRING",
          nullable: false,
          comment: "Declared lifecycle status.",
          classification: "Internal",
          key: "None",
        },
      ],
    },
  );
  add(
    "accounts",
    "customer.core.accounts",
    "table",
    "customer-core",
    "uc-customer",
    {
      knowledgeIds: ["account"],
      fields: [
        {
          path: "account_id",
          type: "BIGINT",
          nullable: false,
          comment: "Account identifier.",
          classification: "Internal",
          key: "Declared primary key",
        },
        {
          path: "customer_id",
          type: "BIGINT",
          nullable: false,
          comment: "Customer relationship.",
          classification: "Internal identifier",
          key: "Declared foreign key",
        },
      ],
    },
  );
  add(
    "unmapped",
    "customer.core.contact_preferences",
    "table",
    "customer-core",
  );
  add(
    "active-view",
    "customer.metrics.active_customers",
    "metric_view",
    "customer-metrics",
    "uc-customer",
    { knowledgeIds: ["active-customers", "active-customer"] },
  );
  add(
    "churn-view",
    "customer.metrics.churn_rate",
    "view",
    "customer-metrics",
    "uc-customer",
    { knowledgeIds: ["churn-rate"], observedAt: START - 30 * 3600000 },
  );
  add("operations-catalog", "operations", "catalog", null);
  add("operations-core", "operations.core", "schema", "operations-catalog");
  add(
    "services",
    "operations.core.services",
    "table",
    "operations-core",
    "uc-customer",
    {
      knowledgeIds: ["service-concept"],
      fields: [
        {
          path: "service_id",
          type: "BIGINT",
          nullable: false,
          comment: "Service identity.",
          classification: "Internal",
          key: "Declared primary key",
        },
        {
          path: "customer_id",
          type: "BIGINT",
          nullable: false,
          comment: "Customer reference.",
          classification: "Internal",
          key: "Declared foreign key",
        },
        {
          path: "service_status",
          type: "STRING",
          nullable: false,
          comment: "Effective service status.",
          classification: "Internal",
          key: "None",
        },
        {
          path: "reporting_date",
          type: "DATE",
          nullable: false,
          comment: "Business reporting date.",
          classification: "Internal",
          key: "None",
        },
      ],
    },
  );
  add("finance-catalog", "finance", "catalog", null, "uc-finance");
  add(
    "finance-metrics",
    "finance.metrics",
    "schema",
    "finance-catalog",
    "uc-finance",
  );
  add(
    "mrr-view",
    "finance.metrics.monthly_recurring_revenue",
    "metric_view",
    "finance-metrics",
    "uc-finance",
    { knowledgeIds: ["mrr"], restricted: true },
  );
  add("duplicate", "customer.core.customers", "table", null, "uc-finance", {
    description:
      "Separate metastore identity; not the Customer workspace table.",
  });
  add(
    "hidden-asset",
    "finance.private.acquisitions",
    "table",
    null,
    "uc-finance",
    { hidden: true },
  );
  const rel = (
    id: string,
    source: string,
    target: string,
    type: Relationship["type"],
    label: string,
  ): Relationship => ({
    id,
    source,
    target,
    type,
    label,
    scope: "Declared fixture",
    cardinality:
      type === "join" ? "many to one (declared, unverified)" : "unspecified",
    provenance:
      type === "lineage"
        ? "UC native lineage fixture"
        : "UOL curated declaration",
    approval: "Approved",
  });
  const relationships = [
    rel("holds", "customer-entity", "account", "business", "holds"),
    rel("groups", "account", "service-concept", "business", "groups"),
    rel("subtype", "individual", "customer-entity", "is_a", "is a"),
    rel("composition", "contract-line", "contract", "part_of", "part of"),
    rel(
      "qualifies",
      "active-customer",
      "customer-entity",
      "business",
      "qualifies",
    ),
    rel(
      "billing-qualifies",
      "billing-active",
      "customer-entity",
      "business",
      "qualifies",
    ),
    rel(
      "metric-dependency",
      "active-customers",
      "active-customer",
      "dependency",
      "defined by",
    ),
    rel(
      "page-dependency",
      "lifecycle-page",
      "active-customer",
      "dependency",
      "documents",
    ),
    rel("native-lineage", "services", "active-view", "lineage", "upstream of"),
    {
      ...rel(
        "declared-join",
        "services",
        "customers",
        "join",
        "customer reference",
      ),
      sourceField: "customer_id",
      targetField: "customer_id",
    },
    rel("private-edge", "hidden-asset", "mrr-view", "lineage", "upstream of"),
  ];
  const metric = {
    version: "1.1",
    source: "operations.core.services",
    filter: "service_status = 'ACTIVE'",
    joins: [
      {
        name: "customers",
        source: "customer.core.customers",
        on: "source.customer_id = customers.customer_id",
      },
    ],
    fields: [
      {
        name: "reporting_date",
        expr: "reporting_date",
        display_name: "Reporting date",
        synonyms: ["As-of date"],
      },
    ],
    measures: [
      {
        name: "active_customers",
        expr: "COUNT(DISTINCT customer_id)",
        display_name: "Active customers",
        synonyms: ["Live customers"],
        format: {
          type: "number",
          decimal_places: { type: "exact", places: 0 },
        },
      },
    ],
  };
  return {
    domains: initialDomains.map((d: any) => ({
      ...d,
      ttl: d.id === "enterprise" ? null : d.ttl,
      steward: d.id === "enterprise" ? "Data Stewardship" : null,
      providerPolicy:
        d.id === "enterprise" ? "Ordered, first sufficient" : null,
    })),
    knowledge,
    providers,
    assets,
    relationships,
    mappings: [
      {
        id: "map-customer",
        knowledgeId: "customer-entity",
        attribute: "identity",
        assetId: "customers",
        fieldPath: "customer_id",
        type: "concept attribute",
        scope: "Enterprise",
        validFrom: "2026-10-01",
        evidence: "Reviewed metadata contract",
        status: "Approved",
      },
      {
        id: "map-active",
        knowledgeId: "active-customers",
        attribute: "measure",
        assetId: "active-view",
        fieldPath: "active_customers",
        type: "metric input",
        scope: "Service",
        validFrom: "2026-10-01",
        evidence: "Metric definition v7",
        status: "Approved",
      },
      {
        id: "map-status1",
        knowledgeId: "active-customer",
        attribute: "eligibility",
        assetId: "customers",
        fieldPath: "status",
        type: "concept attribute",
        scope: "Service",
        validFrom: "2026-10-01",
        evidence: "Proposed service interpretation",
        status: "Draft",
      },
      {
        id: "map-status2",
        knowledgeId: "billing-active",
        attribute: "eligibility",
        assetId: "customers",
        fieldPath: "status",
        type: "concept attribute",
        scope: "Billing",
        validFrom: "2026-10-01",
        evidence: "Competing billing interpretation",
        status: "Draft",
      },
    ],
    cache: [],
    observations: [],
    proposals: [],
    deliveries: [],
    targets: [
      ...assets.map((a) => ({
        id: a.id,
        name: a.name,
        kind: a.type,
        providerId: a.providerId,
        revision: 1,
        content: {
          description: a.description,
          tags: { ...a.tags },
          ...(a.id === "active-view" ? { yaml: metric } : {}),
        },
        capability: "permitted" as const,
        permission: "permitted" as const,
        audience: a.restricted
          ? "Finance stewards"
          : "Internal metadata readers",
        atomic: false,
        failNext: false,
        mismatchNext: false,
        origins: {},
      })),
      {
        id: "genie-customer",
        name: "Customer intelligence",
        kind: "genie",
        providerId: "uc-customer",
        revision: 1,
        content: {
          serialized_space: {
            version: 2,
            config: {
              sample_questions: [
                { id: "q1", question: ["How is an active customer defined?"] },
              ],
            },
            data_sources: {
              tables: [
                { identifier: "customer.core.customers" },
                { identifier: "operations.core.services" },
              ],
              metric_views: [
                { identifier: "customer.metrics.active_customers" },
              ],
            },
            instructions: {
              text_instructions: [
                {
                  id: "i1",
                  content: ["Use service scope for customer activity."],
                },
              ],
              example_question_sqls: [
                {
                  id: "sql1",
                  question: ["Active customers by date"],
                  sql: [
                    "SELECT reporting_date, MEASURE(active_customers) FROM customer.metrics.active_customers GROUP BY reporting_date",
                  ],
                },
              ],
              join_specs: [
                {
                  id: "j1",
                  left: { identifier: "operations.core.services" },
                  right: { identifier: "customer.core.customers" },
                  sql: ["services.customer_id = customers.customer_id"],
                },
              ],
            },
            benchmarks: {
              questions: [
                {
                  id: "b1",
                  question: ["Explain the reporting grain."],
                  answer: [
                    {
                      format: "TEXT",
                      content: ["Customer by reporting date."],
                    },
                  ],
                },
              ],
            },
          },
          unrelated_setting: "Preserve this existing setting",
        },
        capability: "permitted",
        permission: "permitted",
        audience: "Internal metadata readers",
        atomic: true,
        failNext: false,
        mismatchNext: false,
        origins: {},
      },
      {
        id: "page-lifecycle",
        name: "Customer lifecycle",
        kind: "page",
        providerId: "uc-customer",
        revision: 1,
        content: { summary: "A guide to lifecycle definitions." },
        capability: "unsupported",
        permission: "unknown",
        audience: "Internal metadata readers",
        atomic: false,
        failNext: false,
        mismatchNext: false,
        origins: {},
      },
    ],
    pages: [
      {
        id: "lifecycle-page",
        name: "Customer lifecycle",
        domain: "lifecycle",
        owner: "Customer Experience",
        synonyms: ["Customer journey"],
        summary: "Definitions and transitions across the service relationship.",
        body: "Use the Service meaning of Active customer for lifecycle reporting. Billing eligibility is a separate meaning. Review suspended services explicitly.",
        relatedAssets: ["customers", "services"],
        sources: [
          "pages/customer-lifecycle.md",
          "policy/service-eligibility.yaml",
        ],
        state: "Draft",
      },
    ],
    clock: START,
    policyVersion: 1,
    configVersion: 1,
    sequence: 1,
    ttlDismissed: false,
  };
}
