/**
 * Hand-written demo datasets. Content is fictional: questions about the docs of
 * an imaginary CI service ("Lumen CI") and traces from an imaginary support agent.
 */
import type { ToolSpec } from "../types";

// ---------------------------------------------------------------------------
// RAG: rag_qa
// ---------------------------------------------------------------------------

/** Ground truth for one variant of a RAG case. Levels are 0..4. */
export interface RagTruth {
  ctx: string[];
  /** relevance level of each passage to the question */
  rel: number[];
  answer: string;
  /** sentence indices of `answer` that the context does not support */
  unsupported?: number[];
  /** sentence indices that are genuinely ambiguous (hard for a fast judge) */
  hard?: number[];
  relevance?: number;
  correct?: number;
  recall?: boolean;
}

export interface RagCase extends RagTruth {
  id: string;
  question: string;
  expected: string;
  /** what BM25-only retrieval (the baseline) produced instead */
  baseline?: Partial<RagTruth>;
  /** what the prompt-v2 candidate produced instead */
  v2?: Partial<RagTruth>;
}

export const RAG_CASES: RagCase[] = [
  {
    id: "rag-001",
    question: "How long are build logs kept on the Free plan?",
    ctx: [
      "Build logs are retained for 30 days on the Free plan. Team and Enterprise plans retain logs for 400 days.",
      "Artifacts uploaded with `lumen artifacts push` follow the same retention window as logs unless a custom retention is set.",
      "The Free plan includes 2,000 build minutes per month on hosted runners.",
    ],
    rel: [4, 2, 0],
    answer: "Build logs are kept for 30 days on the Free plan. Team and Enterprise plans keep them for 400 days.",
    expected: "30 days",
    v2: {
      answer:
        "Build logs are kept for 30 days on the Free plan. You can extend this to 90 days with the Logs add-on.",
      unsupported: [1],
    },
  },
  {
    id: "rag-002",
    question: "Can I run jobs on ARM runners?",
    ctx: [
      "Hosted runners are available for linux/amd64 and linux/arm64. macOS runners run on Apple silicon.",
      "Select an architecture with `runs-on: lumen-ubuntu-24-arm` in the job definition.",
      "Windows runners are x64 only.",
    ],
    rel: [4, 4, 2],
    answer:
      "Yes. Hosted Linux runners support arm64; set `runs-on: lumen-ubuntu-24-arm` in the job. macOS runners also run on Apple silicon.",
    expected: "Yes, via linux/arm64 hosted runners (runs-on: lumen-ubuntu-24-arm).",
    correct: 4,
  },
  {
    id: "rag-003",
    question: "What is the maximum job timeout?",
    ctx: [
      "Jobs time out after 6 hours by default.",
      "Set `timeout-minutes` to change it. The maximum is 12 hours on hosted runners and 72 hours on self-hosted runners.",
      "Pipelines as a whole are cancelled after 35 days.",
    ],
    rel: [3, 4, 1],
    answer:
      "The default is 6 hours. You can raise it with `timeout-minutes` up to 12 hours on hosted runners or 72 hours on self-hosted runners.",
    expected: "12 hours on hosted runners, 72 hours on self-hosted runners",
    correct: 4,
    baseline: {
      ctx: [
        "Jobs time out after 6 hours by default.",
        "Set `timeout-minutes` to change it. The maximum is 12 hours on hosted runners and 72 hours on self-hosted runners.",
        "Build minutes reset on the first day of each calendar month.",
      ],
      rel: [3, 4, 0],
    },
    v2: {
      answer: "The default is 6 hours. You can raise it with `timeout-minutes` up to 24 hours on any runner.",
      unsupported: [1],
      correct: 1,
    },
  },
  {
    id: "rag-004",
    question: "How do I cache node_modules between builds?",
    ctx: [
      "Use the `cache` step with a key and a path, for example `key: npm-{{ hashFiles('package-lock.json') }}` and `path: ~/.npm`.",
      "Caching `node_modules` directly is supported but not recommended; cache the npm download cache and run `npm ci` instead.",
      "Caches are scoped to the branch and fall back to the default branch.",
    ],
    rel: [4, 4, 3],
    answer:
      "Add a `cache` step keyed on the hash of package-lock.json. Cache ~/.npm rather than node_modules and run `npm ci` so installs stay reproducible.",
    expected: "Use the cache step keyed on package-lock.json; prefer caching ~/.npm and running npm ci.",
    correct: 4,
  },
  {
    id: "rag-005",
    question: "Are secrets available to pull requests from forks?",
    ctx: [
      "Secrets are not passed to pipelines triggered by pull requests from forks.",
      "Fork pipelines receive a read-only `LUMEN_TOKEN` scoped to the repository.",
      "Maintainers can approve a fork pipeline to run with secrets after reviewing the diff.",
    ],
    rel: [4, 3, 4],
    answer:
      "No. Fork pull requests run without secrets and only get a read-only LUMEN_TOKEN. A maintainer can approve the run to grant secrets after reviewing the changes.",
    hard: [2],
    expected: "No, unless a maintainer approves the run; forks only get a read-only LUMEN_TOKEN.",
    correct: 4,
  },
  {
    id: "rag-006",
    question: "How many concurrent jobs does the Team plan include?",
    ctx: [
      "The Team plan includes 20 concurrent jobs on hosted runners.",
      "Additional concurrency can be purchased in blocks of 10.",
      "Self-hosted runners do not count toward concurrency limits.",
    ],
    rel: [4, 3, 3],
    answer:
      "The Team plan includes 20 concurrent hosted jobs, and you can buy more in blocks of 10. Self-hosted runners don't count toward the limit.",
    expected: "20",
    v2: {
      answer:
        "The Team plan includes 20 concurrent hosted jobs, and you can buy more in blocks of 10. Enterprise plans have unlimited concurrency.",
      unsupported: [1],
    },
  },
  {
    id: "rag-007",
    question: "How do I retry only the failed jobs in a pipeline?",
    ctx: [
      "Open the pipeline and choose Re-run failed jobs, or run `lumen pipeline retry <id> --failed`.",
      "Retried jobs reuse the original commit and pipeline variables.",
      "Pipelines older than 30 days cannot be retried.",
    ],
    rel: [4, 3, 2],
    answer:
      "Use Re-run failed jobs in the pipeline view, or run `lumen pipeline retry <id> --failed`. Retries reuse the original commit and variables.",
    expected: "Re-run failed jobs, or lumen pipeline retry <id> --failed",
    correct: 4,
  },
  {
    id: "rag-008",
    question: "Does Lumen support OIDC for cloud deployments?",
    ctx: [
      "Lumen issues OIDC tokens that AWS, GCP and Azure can trust for short-lived credentials.",
      "Request a token with `permissions: id-token: write` on the job.",
      "The token audience defaults to the repository URL.",
    ],
    rel: [4, 4, 2],
    answer:
      "Yes. Grant `id-token: write` on the job and Lumen will issue an OIDC token that AWS, GCP or Azure can exchange for short-lived credentials.",
    expected: "Yes, with permissions id-token: write.",
    correct: 4,
    baseline: {
      ctx: [
        "Lumen issues OIDC tokens that AWS, GCP and Azure can trust for short-lived credentials.",
        "Request a token with `permissions: id-token: write` on the job.",
        "Deploy keys can be rotated from the repository settings page.",
      ],
      rel: [4, 4, 0],
    },
  },
  {
    id: "rag-009",
    question: "What happens when the cache exceeds 10 GB?",
    ctx: [
      "Each repository can store up to 10 GB of caches.",
      "When the limit is exceeded, the least recently used caches are evicted until usage is below the limit.",
      "Caches not accessed for 7 days are removed automatically.",
    ],
    rel: [4, 4, 3],
    answer:
      "When a repository goes over 10 GB, the least recently used caches are evicted until it's back under the limit.",
    expected: "Least recently used caches are evicted.",
    correct: 4,
    v2: {
      answer:
        "When a repository goes over 10 GB, new cache writes are rejected. You need to delete old caches manually to free space.",
      unsupported: [0, 1],
      correct: 0,
      relevance: 3,
    },
  },
  {
    id: "rag-010",
    question: "How do I skip CI for a commit?",
    ctx: [
      "Add `[skip ci]` or `[ci skip]` anywhere in the commit message to skip pipelines for that push.",
      "Skip directives are ignored for tag pushes and scheduled pipelines.",
      "Pull request pipelines use the message of the head commit.",
    ],
    rel: [4, 3, 2],
    answer: "Put `[skip ci]` (or `[ci skip]`) in the commit message. It has no effect on tag pushes or scheduled pipelines.",
    expected: "[skip ci] in the commit message",
  },
  {
    id: "rag-011",
    question: "Can I pin a runner image version?",
    ctx: [
      "Runner images are updated weekly. Labels such as `lumen-ubuntu-24` always point to the latest image.",
      "Pin an image by using a dated label, for example `lumen-ubuntu-24@2026-09-01`.",
      "Dated images are available for 90 days.",
    ],
    rel: [3, 4, 4],
    answer: "Yes. Use a dated label like `lumen-ubuntu-24@2026-09-01`. Dated images remain available for 90 days.",
    expected: "Yes, with a dated label; kept for 90 days.",
    correct: 4,
  },
  {
    id: "rag-012",
    question: "Where are build artifacts stored and for how long?",
    ctx: [
      "Artifacts are stored in Lumen object storage in the data region of your organization.",
      "Default artifact retention matches the log retention of your plan.",
      "Artifacts larger than 5 GB must be uploaded with `lumen artifacts push --multipart`.",
    ],
    rel: [4, 4, 2],
    answer:
      "Artifacts are stored in Lumen object storage in your organization's data region. They are kept for 30 days on Free and 400 days on Team and Enterprise.",
    unsupported: [1],
    hard: [1],
    expected: "Lumen object storage in the org's data region; same retention as logs.",
    relevance: 3,
    correct: 3,
    baseline: {
      ctx: [
        "Artifacts are stored in Lumen object storage in the data region of your organization.",
        "Default artifact retention matches the log retention of your plan.",
        "Logs can be downloaded as a zip archive from the job page.",
      ],
      rel: [4, 4, 1],
    },
  },
  {
    id: "rag-013",
    question: "How do I trigger a pipeline on a schedule?",
    ctx: [
      "Add a `schedule` trigger with a cron expression, for example `cron: '0 3 * * 1-5'`.",
      "Schedules run in UTC and use the default branch.",
      "Scheduled pipelines are paused after 60 days without repository activity.",
    ],
    rel: [4, 4, 3],
    answer:
      "Add a `schedule` trigger with a cron expression such as `0 3 * * 1-5`. Schedules run in UTC on the default branch.",
    expected: "schedule trigger with a cron expression (UTC)",
    correct: 4,
  },
  {
    id: "rag-014",
    question: "Is there a limit on matrix jobs?",
    ctx: [
      "A matrix can generate up to 256 jobs per pipeline run.",
      "Use `max-parallel` to limit how many matrix jobs run at once.",
      "Matrix values can be strings, numbers or booleans.",
    ],
    rel: [4, 3, 1],
    answer: "Yes, a matrix can produce at most 256 jobs per run. Use `max-parallel` to cap how many run at the same time.",
    expected: "256 jobs per run",
    baseline: {
      ctx: [
        "A matrix can generate up to 256 jobs per pipeline run.",
        "Matrix jobs share the pipeline cache.",
        "Matrix values can be strings, numbers or booleans.",
      ],
      rel: [4, 1, 1],
      answer: "Yes, a matrix can produce at most 256 jobs per run.",
    },
  },
  {
    id: "rag-015",
    question: "How do I run a step only on the main branch?",
    ctx: [
      "Every step accepts an `if` expression evaluated before the step runs.",
      "Use `if: lumen.branch == 'main'` to restrict a step to the main branch.",
      "Expressions can reference variables, the presence of secrets and previous step outcomes.",
    ],
    rel: [3, 4, 2],
    answer: "Add `if: lumen.branch == 'main'` to the step.",
    expected: "if: lumen.branch == 'main'",
  },
  {
    id: "rag-016",
    question: "What IP ranges do hosted runners use?",
    ctx: [
      "Hosted runner IP ranges are published at https://api.lumen.dev/meta under `runners`.",
      "Ranges can change without notice; automate allowlist updates from the meta endpoint.",
      "Static egress IPs are available on the Enterprise plan.",
    ],
    rel: [4, 4, 3],
    answer:
      "They're published at https://api.lumen.dev/meta under `runners` and can change without notice, so update allowlists automatically. Enterprise plans can get static egress IPs.",
    expected: "Published at the /meta endpoint; ranges change; Enterprise has static egress IPs.",
    relevance: 3,
    correct: 4,
  },
  {
    id: "rag-017",
    question: "Can I use Docker Compose in a job?",
    ctx: [
      "Docker and Docker Compose v2 are preinstalled on Linux hosted runners.",
      "Services declared under `services:` start before the first step and share a network with the job.",
      "Privileged containers are not allowed on hosted runners.",
    ],
    rel: [4, 3, 2],
    answer: "Yes. Docker Compose v2 is preinstalled on Linux hosted runners, so you can run `docker compose up` in a step.",
    expected: "Yes, Compose v2 is preinstalled on Linux hosted runners.",
    correct: 4,
  },
  {
    id: "rag-018",
    question: "How do I cancel older runs when a new commit is pushed?",
    ctx: [
      "Set `concurrency: { group: ${{ lumen.ref }}, cancel-in-progress: true }` at the pipeline level.",
      "Only pipelines in the same concurrency group are cancelled.",
      "Cancelled pipelines stop consuming build minutes once cancellation completes.",
    ],
    rel: [4, 3, 2],
    answer:
      "Set a concurrency group on the ref with `cancel-in-progress: true`. Newer pushes then cancel older runs in the same group.",
    expected: "concurrency group with cancel-in-progress: true",
    correct: 4,
    v2: {
      answer:
        "Set a concurrency group on the ref with `cancel-in-progress: true`. Cancelled runs are refunded as build credits.",
      unsupported: [1],
      hard: [1],
    },
  },
  {
    id: "rag-019",
    question: "Which regions can store build data?",
    ctx: [
      "Organizations choose a data region at creation: US, EU or APAC.",
      "The data region cannot be changed after creation.",
      "Hosted runners may execute in any region unless data residency is enforced.",
    ],
    rel: [4, 4, 3],
    answer: "US, EU or APAC. The region is picked when the organization is created and can't be changed later.",
    expected: "US, EU, APAC",
  },
  {
    id: "rag-020",
    question: "How do I debug a failing job interactively?",
    ctx: [
      "Re-run a job with debug enabled to get an SSH session: `lumen job retry <id> --ssh`.",
      "The session stays open for 30 minutes after the job fails.",
      "Debug sessions are not available for fork pipelines.",
    ],
    rel: [4, 3, 3],
    answer: "Re-run the job with `lumen job retry <id> --ssh` to get an SSH session. It stays open for 30 minutes after the failure.",
    expected: "lumen job retry <id> --ssh",
    correct: 4,
  },
  {
    id: "rag-021",
    question: "What's the difference between Team and Enterprise support?",
    ctx: [
      "Team plans include business-hours email support.",
      "Enterprise plans include 24/7 support with a 1-hour response time for severity 1 issues.",
      "Enterprise plans include SAML SSO and audit log streaming.",
    ],
    rel: [4, 4, 1],
    answer:
      "Team includes business-hours email support. Enterprise adds 24/7 support with a 1-hour response time for severity 1 issues.",
    expected: "Team: business-hours email support. Enterprise: 24/7 support with a 1-hour severity 1 response time.",
    correct: 4,
    baseline: {
      ctx: [
        "Build logs are retained for 30 days on the Free plan.",
        "Enterprise plans include SAML SSO and audit log streaming.",
        "Hosted runner IP ranges are published at the meta endpoint.",
      ],
      rel: [0, 2, 0],
      answer:
        "Enterprise adds SAML SSO and audit log streaming. The documentation I found doesn't describe support tiers for either plan.",
      recall: false,
      correct: 1,
      relevance: 2,
    },
  },
  {
    id: "rag-022",
    question: "How do I store a secret for a single environment?",
    ctx: [
      "Create environment secrets under Settings → Environments → Secrets.",
      "Environment secrets override repository secrets with the same name.",
      "Jobs must declare `environment: <name>` to receive environment secrets.",
    ],
    rel: [4, 3, 4],
    answer: "Add it under Settings → Environments → Secrets, then set `environment: <name>` on the job that needs it.",
    expected: "Environment secrets, plus environment: <name> on the job.",
    correct: 4,
  },
  {
    id: "rag-023",
    question: "Does Lumen retry flaky tests automatically?",
    ctx: [
      "Lumen does not retry test commands automatically.",
      "Use `retry: { max: 2, when: [runner_failure] }` to retry a job after infrastructure failures.",
      "Test reports uploaded in JUnit format highlight tests that are flaky across runs.",
    ],
    rel: [4, 3, 3],
    answer:
      "No. Lumen only retries jobs you configure with `retry`, and its `when` conditions cover runner failures rather than failing tests. JUnit reports help you spot flaky tests.",
    hard: [1],
    expected: "No; retry only covers configured conditions such as runner failures.",
    correct: 4,
    v2: {
      answer: "Yes. Set `retry: { max: 2 }` and Lumen reruns failing tests up to two times.",
      unsupported: [0, 1],
      correct: 0,
      relevance: 3,
    },
  },
  {
    id: "rag-024",
    question: "What does the `needs` keyword do?",
    ctx: [
      "`needs` declares job dependencies; a job starts only after all jobs it needs succeed.",
      "Jobs without `needs` start in parallel.",
      "Outputs from needed jobs are available as `needs.<job>.outputs`.",
    ],
    rel: [4, 3, 4],
    answer:
      "`needs` makes a job wait for the listed jobs to succeed and lets it read their outputs via `needs.<job>.outputs`. Jobs without it run in parallel.",
    expected: "Declares job dependencies.",
    relevance: 3,
    correct: 3,
  },
];

// ---------------------------------------------------------------------------
// Agent: agent_tasks
// ---------------------------------------------------------------------------

export type SelectionLabel = "appropriate" | "unnecessary" | "wrong_tool";
export type RecoveryLabel = "recovered" | "retried" | "reported" | "ignored";

export interface AgentStep {
  type: "thought" | "tool_call" | "message";
  content?: string;
  tool?: string;
  args?: Record<string, unknown>;
  result?: unknown;
  error?: string;
  ms?: number;
  /** ground truth for per-step judgments */
  sel?: SelectionLabel;
  argsValid?: boolean;
  duplicate?: boolean;
  /** how the agent handled this step's error (failed calls only) */
  rec?: RecoveryLabel;
  note?: string;
}

export interface AgentVariant {
  steps: AgentStep[];
  completion: number; // 0..4
  completionNote: string;
}

export interface AgentCase extends AgentVariant {
  id: string;
  input: string;
  tools: string[];
  expected: { tools: string[]; outcome: string };
  /** the v2-planner candidate's trace, when it differs */
  v2?: AgentVariant;
}

const obj = (props: Record<string, unknown>, required: string[]) => ({
  type: "object",
  properties: props,
  required,
  additionalProperties: false,
});

export const TOOLS: Record<string, ToolSpec> = {
  lookup_order: {
    name: "lookup_order",
    description: "Fetch an order by id, including status, totals and refund eligibility.",
    parameters: obj({ order_id: { type: "string" } }, ["order_id"]),
  },
  get_shipment_status: {
    name: "get_shipment_status",
    description: "Get carrier tracking events for a shipment.",
    parameters: obj({ tracking_id: { type: "string" } }, ["tracking_id"]),
  },
  issue_refund: {
    name: "issue_refund",
    description: "Refund an order in full or in part. Fails when the order is outside the refund window.",
    parameters: obj(
      {
        order_id: { type: "string" },
        amount: { type: "number", exclusiveMinimum: 0 },
        reason: { type: "string", enum: ["damaged_in_transit", "not_delivered", "changed_mind", "other"] },
      },
      ["order_id", "amount", "reason"],
    ),
  },
  get_weather: {
    name: "get_weather",
    description: "Daily forecast for a city.",
    parameters: obj({ city: { type: "string" }, date: { type: "string", format: "date" } }, ["city", "date"]),
  },
  find_free_slots: {
    name: "find_free_slots",
    description: "Find meeting slots where every attendee is free.",
    parameters: obj(
      {
        attendees: { type: "array", items: { type: "string" } },
        window_start: { type: "string", format: "date-time" },
        window_end: { type: "string", format: "date-time" },
        duration_min: { type: "integer", minimum: 5 },
      },
      ["attendees", "window_start", "window_end", "duration_min"],
    ),
  },
  create_event: {
    name: "create_event",
    description: "Create a calendar event and send invites.",
    parameters: obj(
      {
        title: { type: "string" },
        start: { type: "string", format: "date-time" },
        end: { type: "string", format: "date-time" },
        attendees: { type: "array", items: { type: "string" } },
      },
      ["title", "start", "end", "attendees"],
    ),
  },
  search_invoices: {
    name: "search_invoices",
    description: "Search invoices by customer and status.",
    parameters: obj(
      {
        customer: { type: "string" },
        status: { type: "string", enum: ["paid", "unpaid", "void"] },
        limit: { type: "integer", minimum: 1, maximum: 50 },
      },
      ["customer"],
    ),
  },
  send_email: {
    name: "send_email",
    description: "Send an email from the support mailbox.",
    parameters: obj(
      {
        to: { type: "string", format: "email" },
        subject: { type: "string" },
        body: { type: "string" },
        attachments: { type: "array", items: { type: "string" } },
      },
      ["to", "subject", "body"],
    ),
  },
  list_incidents: {
    name: "list_incidents",
    description: "List incidents by severity and status. `source: cache` reads the last snapshot.",
    parameters: obj(
      {
        severity: { type: "string", enum: ["P1", "P2", "P3"] },
        status: { type: "string", enum: ["open", "resolved"] },
        source: { type: "string", enum: ["live", "cache"] },
      },
      ["severity", "status"],
    ),
  },
  convert_currency: {
    name: "convert_currency",
    description: "Convert an amount between currencies at the latest reference rate.",
    parameters: obj(
      { amount: { type: "number" }, from: { type: "string" }, to: { type: "string" } },
      ["amount", "from", "to"],
    ),
  },
  lookup_user: {
    name: "lookup_user",
    description: "Find a user account by username.",
    parameters: obj({ username: { type: "string" } }, ["username"]),
  },
  reset_password: {
    name: "reset_password",
    description: "Send a password reset link to a user.",
    parameters: obj(
      { user_id: { type: "string", pattern: "^u_[0-9]+$" }, notify: { type: "boolean" } },
      ["user_id", "notify"],
    ),
  },
  create_ticket: {
    name: "create_ticket",
    description: "Create an issue in the tracker.",
    parameters: obj(
      {
        project: { type: "string" },
        title: { type: "string" },
        description: { type: "string" },
        priority: { type: "string", enum: ["low", "medium", "high", "urgent"] },
      },
      ["project", "title", "priority"],
    ),
  },
};

const weatherResult = { city: "Lisbon", date: "2026-09-28", forecast: "light rain", precip_probability: 0.7, high_c: 22, low_c: 16 };

export const AGENT_CASES: AgentCase[] = [
  {
    id: "agent-001",
    input: "Order 48213 arrived damaged. Please refund it.",
    tools: ["lookup_order", "get_shipment_status", "issue_refund"],
    expected: { tools: ["lookup_order", "issue_refund"], outcome: "Full refund issued for order 48213" },
    steps: [
      { type: "thought", content: "The customer wants a refund for a damaged order. Look the order up first to get the amount and eligibility." },
      {
        type: "tool_call",
        tool: "lookup_order",
        args: { order_id: "48213" },
        result: { order_id: "48213", status: "delivered", total: 64.9, currency: "USD", tracking_id: "1Z94X", refundable: true },
        ms: 212,
      },
      {
        type: "tool_call",
        tool: "get_shipment_status",
        args: { tracking_id: "1Z94X" },
        result: { status: "delivered", delivered_at: "2026-09-20", damage_reported: true },
        ms: 348,
      },
      {
        type: "tool_call",
        tool: "issue_refund",
        args: { order_id: "48213", amount: 64.9, reason: "damaged_in_transit" },
        result: { refund_id: "rf_5521", status: "pending" },
        ms: 431,
      },
      {
        type: "message",
        content:
          "I've issued a full refund of $64.90 for order 48213. Refund rf_5521 is pending and should reach your card within 3–5 business days.",
      },
    ],
    completion: 4,
    completionNote:
      "Verified the order and the carrier's damage report, refunded the full amount with the correct reason code, and told the customer when to expect the money.",
  },
  {
    id: "agent-002",
    input: "What's the weather in Lisbon tomorrow? Should I bring an umbrella?",
    tools: ["get_weather"],
    expected: { tools: ["get_weather"], outcome: "Forecast with an umbrella recommendation" },
    steps: [
      { type: "tool_call", tool: "get_weather", args: { city: "Lisbon", date: "2026-09-28" }, result: weatherResult, ms: 286 },
      {
        type: "tool_call",
        tool: "get_weather",
        args: { city: "Lisbon", date: "2026-09-28" },
        result: weatherResult,
        ms: 274,
        sel: "unnecessary",
        duplicate: true,
        note: "Repeats the previous get_weather call with identical arguments.",
      },
      {
        type: "message",
        content: "Tomorrow in Lisbon: light rain, a 70% chance of precipitation and a high of 22 °C. Bring an umbrella.",
      },
    ],
    completion: 4,
    completionNote: "Correct forecast and a clear recommendation. The duplicate lookup cost time but did not change the outcome.",
    v2: {
      steps: [
        { type: "tool_call", tool: "get_weather", args: { city: "Lisbon", date: "2026-09-28" }, result: weatherResult, ms: 291 },
        {
          type: "message",
          content: "Tomorrow in Lisbon: light rain, a 70% chance of precipitation and a high of 22 °C. Bring an umbrella.",
        },
      ],
      completion: 4,
      completionNote: "Single lookup, correct forecast and a clear recommendation.",
    },
  },
  {
    id: "agent-003",
    input: "Book 30 minutes with Dana next Tuesday afternoon.",
    tools: ["find_free_slots", "create_event"],
    expected: { tools: ["find_free_slots", "create_event"], outcome: "30-minute event with Dana on Tuesday afternoon" },
    steps: [
      { type: "thought", content: "Find a slot where both calendars are free on Tuesday Sep 29 between 12:00 and 18:00." },
      {
        type: "tool_call",
        tool: "find_free_slots",
        args: {
          attendees: ["me", "dana@northwind.dev"],
          window_start: "2026-09-29T12:00:00",
          window_end: "2026-09-29T18:00:00",
          duration_min: 30,
        },
        result: { slots: ["2026-09-29T14:00:00", "2026-09-29T16:30:00"] },
        ms: 388,
      },
      {
        type: "tool_call",
        tool: "create_event",
        args: {
          title: "Sync with Dana",
          start: "2026-09-29T14:00:00",
          end: "2026-09-29T14:30:00",
          attendees: ["dana@northwind.dev"],
        },
        result: { event_id: "ev_88a1", status: "confirmed" },
        ms: 502,
      },
      { type: "message", content: "Booked “Sync with Dana” for Tuesday Sep 29, 14:00–14:30. Dana has the invite." },
    ],
    completion: 4,
    completionNote: "Found a mutually free slot inside the requested window and booked a 30-minute event with Dana.",
  },
  {
    id: "agent-004",
    input: "Find ACME's latest unpaid invoice and email it to finance.",
    tools: ["search_invoices", "send_email"],
    expected: { tools: ["search_invoices", "send_email"], outcome: "Latest unpaid ACME invoice sent to finance" },
    steps: [
      {
        type: "tool_call",
        tool: "search_invoices",
        args: { customer: "ACME", status: "unpaid", limit: 1 },
        result: { invoices: [{ id: "INV-2291", amount: 12400, currency: "USD", due: "2026-10-05" }] },
        ms: 264,
      },
      {
        type: "tool_call",
        tool: "send_email",
        args: {
          to: "finance@northwind.dev",
          subject: "ACME invoice INV-2291 (unpaid, due Oct 5)",
          body: "Hi team, attached is ACME's latest unpaid invoice, INV-2291, for $12,400, due October 5.",
          attachments: ["INV-2291"],
        },
        result: { message_id: "msg_1a2f" },
        ms: 611,
      },
      { type: "message", content: "Sent INV-2291 ($12,400, due Oct 5) to finance@northwind.dev." },
    ],
    completion: 4,
    completionNote: "Located the latest unpaid ACME invoice and sent it to the finance mailbox with the invoice attached.",
  },
  {
    id: "agent-005",
    input: "Summarize the open P1 incidents.",
    tools: ["list_incidents"],
    expected: { tools: ["list_incidents"], outcome: "Summary of open P1 incidents" },
    steps: [
      {
        type: "tool_call",
        tool: "list_incidents",
        args: { severity: "P1", status: "open" },
        error: "503 Service Unavailable: incident service timed out after 10s",
        ms: 10012,
        rec: "retried",
        note: "Retried the call, which is reasonable once for a timeout.",
      },
      {
        type: "tool_call",
        tool: "list_incidents",
        args: { severity: "P1", status: "open" },
        error: "503 Service Unavailable: incident service timed out after 10s",
        ms: 10008,
        rec: "reported",
        duplicate: true,
        sel: "unnecessary",
        note: "Second identical retry; the cached source was available but not tried.",
      },
      {
        type: "message",
        content:
          "I couldn't reach the incident service, so I can't list the open P1 incidents right now. Please try again shortly or check the status page.",
      },
    ],
    completion: 1,
    completionNote:
      "The incident service timed out and the agent retried once with identical arguments, then gave up. It was honest about the failure, but the user got no summary even though a cached source existed.",
    v2: {
      steps: [
        {
          type: "tool_call",
          tool: "list_incidents",
          args: { severity: "P1", status: "open" },
          error: "503 Service Unavailable: incident service timed out after 10s",
          ms: 10010,
          rec: "recovered",
          note: "Fell back to the cached incident snapshot on the next step.",
        },
        {
          type: "tool_call",
          tool: "list_incidents",
          args: { severity: "P1", status: "open", source: "cache" },
          result: {
            as_of: "2026-09-27T09:52:00Z",
            incidents: [
              { id: "INC-4410", title: "EU checkout latency above SLO", started: "2026-09-27T08:10:00Z" },
              { id: "INC-4412", title: "Webhook deliveries delayed for 3% of tenants", started: "2026-09-27T09:31:00Z" },
            ],
          },
          ms: 143,
        },
        {
          type: "message",
          content:
            "Two P1 incidents are open (from the 09:52 UTC snapshot; the live service is timing out): INC-4410, EU checkout latency above SLO since 08:10, and INC-4412, delayed webhook deliveries for about 3% of tenants since 09:31.",
        },
      ],
      completion: 3,
      completionNote:
        "After the live call failed, the agent read the cached snapshot and summarized both open P1 incidents, flagging that the data may be a few minutes old.",
    },
  },
  {
    id: "agent-006",
    input: "Convert 250 EUR to JPY.",
    tools: ["convert_currency"],
    expected: { tools: ["convert_currency"], outcome: "Converted amount with rate" },
    steps: [
      {
        type: "tool_call",
        tool: "convert_currency",
        args: { amount: 250, from: "EUR", to: "JPY" },
        result: { amount: 40912.5, rate: 163.65, as_of: "2026-09-27T08:00:00Z" },
        ms: 167,
      },
      { type: "message", content: "250 EUR is about ¥40,913 at 163.65 JPY per EUR (reference rate from 08:00 UTC today)." },
    ],
    completion: 4,
    completionNote: "Correct conversion, with the rate and its timestamp stated.",
  },
  {
    id: "agent-007",
    input: "Reset the password for user jlee and let them know.",
    tools: ["lookup_user", "reset_password"],
    expected: { tools: ["lookup_user", "reset_password"], outcome: "Reset link sent to jlee" },
    steps: [
      {
        type: "tool_call",
        tool: "lookup_user",
        args: { username: "jlee" },
        result: { user_id: "u_1042", email: "j.lee@northwind.dev", status: "active" },
        ms: 198,
      },
      {
        type: "tool_call",
        tool: "reset_password",
        args: { user_id: "jlee", notify: "yes" },
        error: "invalid arguments: user_id must match ^u_[0-9]+$; notify must be a boolean",
        ms: 41,
        argsValid: false,
        rec: "recovered",
        note: "Passed the username instead of the user id, and a string for a boolean.",
      },
      {
        type: "tool_call",
        tool: "reset_password",
        args: { user_id: "u_1042", notify: true },
        result: { status: "reset_link_sent" },
        ms: 356,
      },
      { type: "message", content: "Done. A password reset link was sent to j.lee@northwind.dev." },
    ],
    completion: 4,
    completionNote: "The first reset call used the username instead of the user id, but the agent corrected it and completed the reset.",
    v2: {
      steps: [
        {
          type: "tool_call",
          tool: "lookup_user",
          args: { username: "jlee" },
          result: { user_id: "u_1042", email: "j.lee@northwind.dev", status: "active" },
          ms: 205,
        },
        {
          type: "tool_call",
          tool: "reset_password",
          args: { user_id: "u_1042", notify: true },
          result: { status: "reset_link_sent" },
          ms: 349,
        },
        { type: "message", content: "Done. A password reset link was sent to j.lee@northwind.dev." },
      ],
      completion: 4,
      completionNote: "Looked up the user id and reset the password in one valid call.",
    },
  },
  {
    id: "agent-008",
    input: "Create a high-priority ticket for the login bug on Safari.",
    tools: ["create_ticket", "search_invoices"],
    expected: { tools: ["create_ticket"], outcome: "High-priority WEB ticket for the Safari login bug" },
    steps: [
      { type: "thought", content: "Web app issues are tracked in the WEB project. Check for an existing key first." },
      {
        type: "tool_call",
        tool: "search_invoices",
        args: { customer: "WEB" },
        result: { invoices: [] },
        ms: 233,
        sel: "wrong_tool",
        note: "search_invoices cannot look up tracker projects or existing tickets.",
      },
      {
        type: "tool_call",
        tool: "create_ticket",
        args: {
          project: "WEB",
          title: "Login fails on Safari",
          description: "Users report that the login button does nothing on Safari. Needs reproduction.",
          priority: "high",
        },
        result: { ticket: "WEB-1877", url: "https://tracker.northwind.dev/WEB-1877" },
        ms: 412,
      },
      { type: "message", content: "Created WEB-1877 (high priority): “Login fails on Safari”." },
    ],
    completion: 3,
    completionNote: "Ticket created in the right project with the right priority. The invoice search before it had nothing to do with the task.",
    v2: {
      steps: [
        {
          type: "tool_call",
          tool: "create_ticket",
          args: {
            project: "WEB",
            title: "Login fails on Safari",
            description: "Users report that the login button does nothing on Safari. Needs reproduction.",
            priority: "high",
          },
          result: { ticket: "WEB-1877", url: "https://tracker.northwind.dev/WEB-1877" },
          ms: 398,
        },
        { type: "message", content: "Created WEB-1877 (high priority): “Login fails on Safari”." },
      ],
      completion: 4,
      completionNote: "Created the ticket directly in the right project with the requested priority.",
    },
  },
  {
    id: "agent-009",
    input: "Refund order 50117, the customer changed their mind.",
    tools: ["lookup_order", "issue_refund"],
    expected: { tools: ["lookup_order"], outcome: "Explain that order 50117 is outside the refund window" },
    steps: [
      {
        type: "tool_call",
        tool: "lookup_order",
        args: { order_id: "50117" },
        result: {
          order_id: "50117",
          status: "delivered",
          delivered_at: "2026-08-12",
          total: 129,
          refundable: false,
          refund_block_reason: "outside 30-day refund window",
        },
        ms: 207,
      },
      {
        type: "tool_call",
        tool: "issue_refund",
        args: { order_id: "50117", amount: 129, reason: "changed_mind" },
        error: "refund not allowed: order is outside the refund window",
        ms: 188,
        sel: "unnecessary",
        rec: "reported",
        note: "The lookup already said the order is not refundable.",
      },
      {
        type: "message",
        content:
          "Order 50117 was delivered on Aug 12, which is outside the 30-day refund window, so the refund was declined. I can escalate this to a support lead if you'd like an exception.",
      },
    ],
    completion: 2,
    completionNote:
      "The lookup showed the order was not refundable, yet the agent attempted the refund anyway. It then reported the decline honestly and offered an escalation.",
    v2: {
      steps: [
        {
          type: "tool_call",
          tool: "lookup_order",
          args: { order_id: "50117" },
          result: {
            order_id: "50117",
            status: "delivered",
            delivered_at: "2026-08-12",
            total: 129,
            refundable: false,
            refund_block_reason: "outside 30-day refund window",
          },
          ms: 214,
        },
        {
          type: "message",
          content:
            "Order 50117 was delivered on Aug 12, which is outside the 30-day refund window, so I can't refund it. I can escalate this to a support lead if you'd like an exception.",
        },
      ],
      completion: 4,
      completionNote: "Checked the refund window, explained why the order can't be refunded and offered an escalation without attempting a blocked refund.",
    },
  },
];
