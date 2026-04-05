# FinSpark — PPT Slide Content

---

## Slide 1: Title Slide

**Title:** FinSpark — AI Integration Orchestration Engine

**Subtitle:** Transform Requirement Documents into Production-Ready Integration Configurations

**Tagline:** *"Configure Enterprise Integrations from Intent, Not Code"*

**Team Details:** [Your Team Name / Members]

**Event:** FinSpark Hackathon 2026

---

## Slide 2: The Problem

### Heading: The Enterprise Integration Bottleneck

**The Context:**
Enterprise lending platforms must integrate with 10-20+ external services — credit bureaus (CIBIL, Experian), KYC providers (Karza, DigiLocker), GST services, fraud engines (RiskGuard), payment gateways (Razorpay, Stripe), open banking APIs (Perfios), and messaging (Twilio). Pre-built adapters often exist, but **customer-specific configuration** remains painfully manual.

**Current Manual Process (5-Step Pain):**
1. **Manual Document Analysis** — Implementation teams read 50-100 page BRDs and SOW documents line by line to identify required integrations, API versions, and field mappings.
2. **Repetitive Schema Mapping** — Engineers manually map client-side data fields (e.g., `pan_number`) to each API's expected fields (e.g., `tax_identifier`) — across 10+ integrations, each with different schemas.
3. **Manual API Version Selection** — Teams must manually check which API version to use, whether older versions are deprecated, and what sunset dates apply — often leading to production failures when deprecated versions are unknowingly deployed.
4. **Hook & Transformation Rule Configuration** — Security hooks (encryption, audit logging, credential resolution), retry policies, and data transformation rules are configured by hand for each integration.
5. **Repeated Sandbox Testing Cycles** — Weeks of manual sandbox testing before production deployment, with no structured confidence scoring.

**Key Pain Points:**
- **4-8 weeks** average implementation cycle per client onboarding
- **30-40%** configuration defect rate due to human error
- Multiple API versions must coexist across tenants
- Credential management is scattered and inconsistent
- No auditability of who changed what, when, and why

---

## Slide 3: Our Solution

### Heading: FinSpark — AI-Powered Integration Orchestration

**One-Line Pitch:**
Upload your BRD/SOW documents, our 7-stage AI pipeline automatically extracts requirements, matches adapters, generates production-ready configs, and simulates integrations — **all in minutes, not weeks**.

**Before vs After:**

| Aspect | Before (Manual) | After (FinSpark) |
|---|---|---|
| Document Analysis | Engineers read 100-page BRDs manually | AI extracts all integration signals in seconds |
| Adapter Selection | Team manually searches adapter catalogs | AI auto-matches from versioned adapter registry |
| API Version Selection | Manual version lookup, deprecated versions slip through | Auto-detects deprecated versions, upgrades to latest stable |
| Schema/Field Mapping | Hand-crafted field-by-field for each API | AI generates mappings with reasoning annotations |
| Hook Configuration | Manual setup of 10+ hooks per integration | AI assigns security, audit, retry hooks automatically |
| Config Review | Email chains, spreadsheets | In-app human-in-the-loop review with AI-powered corrections |
| Testing | Weeks of sandbox testing | Automated multi-scenario simulation with confidence scores |
| Time to Production | 4-8 weeks | Minutes to hours |
| Defect Rate | 30-40% | Near-zero (AI + human review + simulation) |
| Audit Trail | Nonexistent | Full SHA-256 hashed, timestamped audit log |

**How It Works (High Level):**
1. Create a project for your client
2. Upload BRD/SOW documents (PDF, DOCX supported)
3. Click "Run Pipeline" — 7 AI stages execute automatically
4. Review the generated config in the dashboard
5. Approve, Simulation runs, Production-ready config delivered

---

## Slide 4: System Architecture

### Heading: End-to-End System Architecture

**Architecture Components:**

```
+-------------------------------------------------------------+
|                    FRONTEND (Next.js 16)                     |
|  Dashboard | Project View | Config Editor | Role Switcher    |
+----------------------------+---------------------------------+
                             | REST API
+----------------------------v---------------------------------+
|                   BACKEND (FastAPI)                          |
|                                                              |
|  +--------------+  +--------------+  +------------------+   |
|  | Project      |  | Audit        |  | Credential       |   |
|  | Service      |  | Service      |  | Service (.env)   |   |
|  +--------------+  +--------------+  +------------------+   |
|                                                              |
|  +------------------------------------------------------+   |
|  |         7-STAGE AI PIPELINE (Orchestrator)            |   |
|  |  S1 > S2 > S3 > S4 > S5 > [PAUSE] S6 > S7           |   |
|  +------------------------------------------------------+   |
|                                                              |
|  +------------------------------------------------------+   |
|  |           LLM SERVICE (Gemini 3.1 Flash Lite)         |   |
|  |   Rate-limit handling | JSON parsing | Retry logic    |   |
|  +------------------------------------------------------+   |
+-------------------------------------------------------------+

+------------------+  +------------------+  +------------------+
|  ADAPTER CATALOG  |  |   HOOK CATALOG    |  |  MOCK RESPONSES   |
|  12 adapters      |  |   14 hooks        |  |  10 services      |
|  master_index.json|  |  master_index.json|  |  success/fail/    |
|  (versioned)      |  |  (lifecycle)      |  |  timeout mocks    |
+------------------+  +------------------+  +------------------+

+--------------------------------------------------------------+
|                    CLIENT DATA (Multi-Tenant)                 |
|  clients/client_{id}/                                         |
|    |-- .env (credential vault)                                |
|    |-- configs/ (config_v1.json, config_v2.json, ...)        |
|    |-- input_documents/ (BRD.docx, SOW.docx)                 |
|    |-- simulation_reports/                                    |
|    |-- diffs/                                                 |
|    +-- audit/audit_log.json                                   |
+--------------------------------------------------------------+
```

**Key Architectural Decisions:**
- **Template-Driven Config Generation:** Every new project starts from `config_v1_template.json` — a standardized schema with metadata, credential vault, integrations array, diff history, audit log, and simulation report sections. The AI fills this template rather than generating freeform configs.
- **File-Based Multi-Tenancy:** Each client gets an isolated folder with its own configs, credentials, documents, reports, and audit logs — zero cross-tenant data leakage.
- **Background Pipeline Execution:** Pipeline runs asynchronously via FastAPI's BackgroundTasks — the frontend polls `/status` for real-time progress updates.
- **Versioned Configs:** Every pipeline run and human correction creates a new config version (config_v1, v2, v3...) — full history is preserved, diffs are computed.

---

## Slide 5: What Makes Our Solution Unique

### Heading: Key Differentiators

**1. Template-Driven Configuration**
- Every project starts from a standardized JSON template (`config_v1_template.json`) with predefined sections: metadata, credential vault, integrations, diff history, audit log, and simulation report.
- The AI fills the template rather than generating arbitrary configs — ensuring structural consistency across all clients.
- Templates can be customized per industry vertical.

**2. Human-in-the-Loop Review (Stage 6)**
- Pipeline automatically pauses before simulation for mandatory human review.
- The reviewer can approve the config OR submit natural-language change requests (e.g., "Remove the Twilio integration" or "Change CIBIL timeout to 10 seconds").
- A **Corrector Agent** (LLM) applies the reviewer's changes and saves a new config version.
- Maximum 3 correction iterations — after that, config is escalated to senior review.
- Simulation (Stage 7) only runs AFTER human approval — no untested configs reach production.

**3. Automatic API Version Upgrade on Deprecation**
- Stage 3 checks each adapter's version registry for deprecation status and sunset dates.
- If the BRD requests a deprecated API version (e.g., CIBIL v1, sunset 2025-06-01), the pipeline auto-upgrades to the latest stable version (e.g., CIBIL v2).
- This decision is logged with a `_version_reason` annotation explaining exactly why the upgrade happened.
- The deprecated flag and sunset_date are deterministically enforced from the adapter catalog — not left to LLM hallucination.

**4. Reasoning Report Generation (Stage 4)**
- After config enrichment, a full markdown reasoning report is generated explaining EVERY pipeline decision.
- Covers: adapter selection rationale, version selection & deprecation notices, missing required fields, unmatched APIs, field mapping summary, and overall assessment.
- This report is displayed alongside the config in the dashboard so the human reviewer understands WHY each decision was made.

**5. Multi-Tenant Role-Based Access**
- Three roles: **Admin** (full access to all projects, credentials, and catalogs), **Standard** (read/write projects but no credentials), **Client** (view their own project and manage their own credentials).
- Role persists across sessions via localStorage.
- The frontend dynamically hides/shows tabs, buttons, and sections based on the active role.

**6. Full Audit Trail**
- Every pipeline stage, every config edit, every review decision emits a structured audit entry with: timestamp, stage, action, agent, responsible party, SHA-256 input/output hashes, and details.
- Stored per-client in `audit/audit_log.json`.
- Viewable in the dashboard's Audit tab.

**7. Credential Vault Isolation**
- API keys and secrets are stored in per-client `.env` files — never in the config JSON.
- Configs reference credentials using `$ENV_VAR_NAME` format (e.g., `$CIBIL_API_KEY`).
- The system auto-detects `$ENV_VAR` references in configs and pre-populates the client's `.env` with empty stubs.
- Admin can manage all credentials; Client can view and edit their own project's credentials via the dashboard.

**8. Config Diff & Version History**
- Every config change (pipeline run, human correction, version migration) creates a new versioned config file.
- Structured diffs are computed between versions showing exactly what changed (added, removed, modified fields).
- Diffs are viewable in the dashboard for full change audit.

---

## Slide 6: Tech Stack

### Heading: Technology Stack

**Backend:**
| Technology | Purpose |
|---|---|
| **Python 3.9+** | Core language |
| **FastAPI** | High-performance async API framework |
| **Uvicorn** | ASGI server |
| **Google Gemini 3.1 Flash Lite** | LLM for document parsing, adapter matching, field mapping, config correction, simulation reports |
| **LangSmith** | LLM observability and tracing (every LLM call is traced) |
| **PyMuPDF (fitz)** | PDF text extraction |
| **python-docx** | DOCX text extraction (paragraphs + tables) |
| **DeepDiff** | JSON config version diffing |
| **Pydantic v2** | Request/response validation and API schemas |
| **python-dotenv** | Environment variable management |

**Frontend:**
| Technology | Purpose |
|---|---|
| **Next.js 16** | React framework with App Router |
| **React 19** | UI library |
| **TypeScript** | Type-safe frontend development |
| **Tailwind CSS 4** | Utility-first styling |
| **react-markdown + remark-gfm** | Rendering reasoning reports in the dashboard |

**Architecture:**
| Pattern | Detail |
|---|---|
| **REST API** | Frontend to Backend communication |
| **Background Tasks** | Pipeline runs asynchronously, frontend polls for status |
| **File-Based Storage** | JSON configs, audit logs, simulation reports — no database needed |
| **Template-Driven Generation** | Standardized config template filled by AI |
| **Multi-Tenant Isolation** | Per-client folder structure |

---

## Slide 7: The 7-Stage AI Pipeline (Overview)

### Heading: End-to-End Pipeline — From Project Creation to Production Config

This slide shows the complete journey from project creation through the 7-stage pipeline.

**Phase 0: Project Initiation (Before Pipeline)**

Before the pipeline runs, a project must be created and documents uploaded. Here is what happens:

1. **Project Creation** — Admin or Standard user clicks "New Project" and enters the client name (e.g., "FinNova Technologies").
2. **Backend Processing:**
   - `project_service.py` generates a unique client ID (e.g., `client_a8f3bc21`) using UUID.
   - Creates the full directory structure under `clients/client_a8f3bc21/`:
     - `input_documents/` — for BRD/SOW uploads
     - `configs/` — for versioned config files
     - `simulation_reports/` — for test results
     - `diffs/` — for config version diffs
     - `audit/` — for audit log
   - Reads the standard config template (`config_v1_template.json`) and injects client metadata:
     - Sets `config_id`, `config_version: v1`, `created_at`, `client_id`, `client_name`
     - Initializes `pipeline_run` with a fresh `run_id`, status `pending`
   - Saves as `configs/config_v1.json`
   - Creates an empty `.env` credential vault file with header comments
   - Emits the first audit event: "Project created for 'FinNova Technologies'"
3. **Document Upload** — User uploads BRD/SOW documents (PDF, DOCX, TXT, or Markdown). Files are saved to `input_documents/`.
4. **Pipeline Trigger** — User clicks "Run Pipeline". The backend launches `run_pipeline_stages_1_to_5()` as a FastAPI BackgroundTask. The frontend begins polling `GET /api/projects/{client_id}/status` for real-time progress.

**Pipeline Flow Diagram:**

```
[Project Created] --> [Documents Uploaded] --> [Pipeline Triggered]
     |
     v
[Stage 1: Ingestion] --> [Stage 2: Parsing] --> [Stage 3: Matching]
     |                        |                       |
     | Extract text from      | LLM detects all       | 6 sub-steps: adapter
     | PDF/DOCX/TXT files     | integration services   | match, config fill,
     |                        | from documents         | hooks, field mapping
     v                        v                       v
[Stage 4: Reasoning] --> [Stage 5: Cleaner] --> [Stage 6: Human Review]
     |                        |                       |
     | LLM generates          | Sanitize config,      | PIPELINE PAUSES.
     | markdown report         | remove annotations,   | Human approves or
     | explaining decisions    | enforce $ENV_VAR      | requests changes.
     |                        |                       |
     |                        |                       v
     |                        |              [Approved? Yes] --> [Stage 7: Simulation]
     |                        |                                        |
     |                        |                                  Loads mock responses,
     |                        |                                  tests each integration,
     |                        |                                  generates confidence
     |                        |                                  score and report.
     |                        |                                        |
     v                        v                                        v
                                                           [PRODUCTION-READY CONFIG]
```

**Pipeline Stats:**
- ~9 LLM calls per full pipeline run
- Background execution with real-time progress polling (5% > 15% > 35% > 60% > 75% > 85% > 90% > 100%)
- Automatic retry with exponential backoff on rate-limit errors (2s, 4s, 8s, 16s, 32s, max 60s)
- Full audit trail emitted at every stage transition

---

## Slide 8: Stage 1 — Document Ingestion (Detailed)

### Heading: Stage 1 — Document Ingestion & Text Extraction

**Purpose:** Extract raw text from all uploaded documents so subsequent stages can analyze them with the LLM.

**How It Works — Step by Step:**

1. **Scan Input Directory** — The stage reads all files from `clients/{client_id}/input_documents/`. It filters for supported extensions: `.pdf`, `.docx`, `.txt`, `.md`, `.markdown`. Unsupported file types are skipped with a warning.

2. **File-Type Detection & Extraction Strategy:**
   - **PDF Files** — Uses PyMuPDF (`fitz`) to open the PDF. Iterates page by page. For each page, `page.get_text()` extracts raw text. Output is formatted with `--- Page N ---` markers separating each page's content.
   - **DOCX Files** — Uses `python-docx` to load the document. Iterates through the document body elements sequentially:
     - **Paragraphs:** Extracts text. If the paragraph has a heading style (Heading 1, Heading 2, etc.), it is converted to markdown heading syntax (`#`, `##`, etc.) to preserve document hierarchy.
     - **Tables:** Each table is extracted row by row. Cell values are joined with pipe `|` delimiters to create a readable text representation.
   - **TXT / Markdown Files** — Direct file read with UTF-8 encoding.

3. **Output Construction** — Returns a Python dict mapping each filename to its extracted text. For example: `{"BRD_FinNova.docx": "# Requirements...", "SOW_Addendum.pdf": "--- Page 1 ---..."}`.

4. **Audit Event** — Emits an audit entry recording: number of documents processed, total characters extracted, and the list of filenames.

**No LLM calls in this stage** — it is a pure code extraction step.

**Progress:** 5% at start, 15% on completion.

---

## Slide 9: Stage 2 — Requirement Parsing Engine (Detailed)

### Heading: Stage 2 — Requirement Parsing Engine

**Purpose:** Analyze the extracted text using the LLM to detect all integration services, fields, and requirements — then fill the config template.

**How It Works — Step by Step:**

**Step 2a: Combine Document Texts**
- All extracted texts from Stage 1 are concatenated into a single combined text with `===== filename =====` separators between documents.

**Step 2b: Load Catalog Context**
- The adapter master index (`master_index.json`) and hook master index are loaded from the catalogs directory. These are passed to the LLM so it knows what adapters and hooks are available to match against.

**Step 2c: Service Extraction (LLM Call 1 of 2)**
- The full combined document text + both catalog indexes are sent to Gemini with a structured system prompt.
- The LLM is instructed to act as an "enterprise integration requirements analyst" and extract ALL integration-related signals.
- The LLM returns a structured JSON with:
  - `services_detected[]` — each detected service contains:
    - `service_name` — e.g., "CIBIL Credit Bureau"
    - `provider` — e.g., "TransUnion CIBIL"
    - `category` — one of: bureau, kyc, payment, banking, gst, fraud, messaging, document
    - `is_mandatory` — true/false based on document language
    - `confidence` — high/medium/low
    - `version_hint` — any version number mentioned in the BRD (e.g., "v2")
    - `endpoint_hints[]` — any URLs mentioned
    - `purpose` — why the service is needed
    - `fields_mentioned[]` — data field names in context of this service
    - `data_types_mentioned[]` — data types referenced
    - `hook_signals[]` — any webhook/callback mentions
  - `general_requirements` — industry vertical, region, security and compliance needs, global data fields
- The LLM is explicitly instructed to never hallucinate services not present in the document.

**Step 2d: Config Template Fill (LLM Call 2 of 2)**
- The extracted requirements + current config template (config_v1.json with client metadata already injected) are sent to Gemini.
- The LLM fills the template with one integration entry per detected service:
  - Sets `integration_id`, `service_name`, `category`, `is_mandatory`, `status: "detected"`
  - Fills `metadata` fields: `industry_vertical`, `region`, `uploaded_documents[]`
- Output is validated: if the LLM returns incomplete structure (missing `metadata` or `integrations`), the missing sections are merged from the original template.
- The filled config is saved back to `configs/config_v1.json`.

**Step 2e: Audit**
- Emits audit event with: number of services detected, first 200 chars of input and output for traceability.

**Progress:** 20% at start, 35% on completion.

---

## Slide 10: Stage 3 — Catalog Matching & Auto-Configuration (Detailed)

### Heading: Stage 3 — Catalog Matching & Config Enrichment (6 Sub-Steps)

**Purpose:** Match each detected service to a real adapter from the catalog, enrich the config with endpoints, auth, hooks, and field mappings.

This is the most complex stage with 6 sequential sub-steps:

**Step 3a: Adapter Matching (LLM Call 1 of 5)**
- Input: The extracted requirements from Stage 2 + the adapter master index.
- The LLM evaluates each detected service against the catalog and selects the best-fit adapter considering:
  - Category alignment (e.g., a bureau requirement matches bureau adapters)
  - Version hints from the BRD (if the BRD mentions "CIBIL v2", prefer that version)
  - Deprecation status (prefer non-deprecated versions)
  - Maturity score (higher is better)
- Output: `matched_adapters[]` — each entry contains `service_name`, `adapter_id`, `recommended_version`, `match_confidence` (high/medium/low), and `reason` (why this adapter was selected).
- Example: "FinNova Credit Check" matched to adapter `cibil`, version `v2`, confidence `high`.

**Step 3b: Selective File Fetch (Pure Code — No LLM)**
- Using the matched adapter IDs from 3a, the system loads ONLY the matched adapter JSON files from the `catalogs/adapters/` directory.
- This avoids loading the entire catalog — only relevant adapter files are read.
- Each adapter file contains: full version details, auth config, required/optional fields, rate limits, timeout, retry policy, sandbox URL, and fallback adapter reference.

**Step 3c: Config Enrichment (LLM Call 2 of 5)**
- The current config + matched adapter details + requirements are sent to Gemini.
- For each integration, the LLM fills in:
  - `adapter_id` — the matched adapter's ID
  - `selected_version` — the recommended version
  - `endpoint_url` — constructed from `base_url` + version-specific endpoint path
  - `auth_type` — from the adapter (e.g., "api_key", "oauth2")
  - `credential_env_vars[]` — as `$VAR_NAME` references (e.g., `["$CIBIL_API_KEY"]`)
  - `timeout_ms` — from the adapter (e.g., 5000)
  - `retry_policy` — from the adapter (e.g., `{"max_retries": 3, "backoff": "exponential"}`)
  - `sandbox_url` — from the adapter
  - `fallback_adapter` — from the adapter (e.g., `"experian"` as fallback for `"cibil"`)
  - `status` — set to `"adapter_matched"`
  - `_adapter_reason` — explains WHY this adapter was chosen
  - `_version_reason` — explains WHY this version was selected; if the BRD requested a deprecated version, explains the auto-upgrade
- **Deterministic Enforcement (Post-LLM Code):** After the LLM returns, the code loops through each integration and force-sets `deprecated` and `sunset_date` from the adapter catalog data. This ensures these critical fields are 100% accurate — not dependent on LLM reliability.
- Config is saved.

**Step 3d: Hook Matching (LLM Call 3 of 5)**
- The hook catalog master index + current integrations are sent to Gemini.
- The LLM assigns appropriate hooks based on rules:
  - Every integration gets: `credential_resolve_hook`, `pre_auth_hook`, `retry_hook`, `on_failure_alert_hook`
  - Bureau/KYC integrations additionally get: `field_encryption_hook`, `post_schema_validation_hook`
  - All integrations benefit from: `post_transform_hook`, `audit_emit_hook`
  - Simulation mode needs: `simulation_intercept_hook`
- Output: `hook_assignments[]` — each entry maps an `integration_id` to a list of `assigned_hooks`.

**Step 3e: Hook Fetch + Fill (LLM Call 4 of 5)**
- All unique hook IDs from 3d are collected. The corresponding hook JSON files are loaded from `catalogs/hooks/`.
- The current config + hook assignments + hook details are sent to Gemini.
- For each integration, the LLM populates the `hooks[]` array with full hook entries:
  - `hook_id`, `hook_name`, `hook_type`
  - `lifecycle_state: "registered"`
  - `execution_order` — determines hook execution sequence
  - `is_blocking` — whether the hook halts the pipeline on failure
  - `trigger_condition` — when the hook fires
  - `timeout_ms` — hook timeout
- Config is saved.

**Step 3f: Field Mapping & Transformation Rules (LLM Call 5 of 5)**
- The current config + requirements + adapter schemas (required_fields, optional_fields, response_schema for each matched adapter) are sent to Gemini.
- For each integration, the LLM generates:
  - `field_mapping[]` — maps user fields from BRD to API fields:
    - `user_field` — e.g., `"pan_number"`
    - `api_field` — e.g., `"tax_identifier"`
    - `mapping_type` — `"direct"` (1:1 name match), `"rename"` (different names, same data), `"computed"` (derived field), or `"missing"` (required API field with no BRD data)
    - `description` — what this mapping does
    - `_mapping_reason` — WHY this mapping was chosen. For `"missing"` type: "Required API field 'X' has no corresponding data in the BRD document. This must be provided at runtime."
  - `transformation_rules[]` — data transformations needed:
    - `source_field`, `target_field`, `rule_type` (type_cast/encrypt/format/compute), `rule`, `example`
    - PII fields (PAN, Aadhaar) get encryption transformation rules automatically
- **Hook Restoration (Post-LLM Code):** If the LLM accidentally drops hooks during field mapping (a known LLM behavior), the code detects this and restores hooks from the pre-3f config version.
- Config is saved.

**Progress:** 40% at start, 60% on completion.

---

## Slide 11: Stage 4 — Reasoning Report Generation (Detailed)

### Heading: Stage 4 — Reasoning Document Generator

**Purpose:** Generate a human-readable markdown report that explains every decision the pipeline made, so the reviewer at Stage 6 can understand WHY each adapter, version, and field mapping was chosen.

**How It Works — Step by Step:**

1. **Load Annotated Config** — Reads the latest config (which still contains `_adapter_reason`, `_version_reason`, and `_mapping_reason` annotations from Stage 3).

2. **Load Raw BRD Text** — Retrieves the original extracted texts from Stage 1. Combines all documents with `---` separators. Truncates to 15,000 characters if needed to stay within LLM context limits.

3. **Truncate Config for Context** — The annotated config JSON is truncated to 30,000 characters if necessary.

4. **LLM Call (1 call)** — The annotated config + raw BRD text are sent to Gemini with a system prompt instructing it to produce a structured markdown reasoning report with the following sections:

   **Section 1: Adapter Selection Rationale**
   - For each integration: which adapter was chosen and why (sourced from `_adapter_reason`)
   - If no adapter matched, flagged as a warning

   **Section 2: Version Selection & Deprecation Notices**
   - For each integration: which version was selected and why (sourced from `_version_reason`)
   - If a version was auto-upgraded because the BRD-requested version is deprecated, clearly explains: old version, new version, and sunset date
   - If the selected version is itself deprecated, adds a deprecation warning

   **Section 3: Missing Required Fields**
   - Scans all `field_mapping` entries with `mapping_type: "missing"`
   - Lists each missing required field by integration
   - Explains why it couldn't be mapped (sourced from `_mapping_reason`)
   - Warns that these must be provided at runtime

   **Section 4: Unmatched APIs / Services**
   - Cross-references the BRD text against the integrations
   - Lists any APIs or services mentioned in the BRD that have NO matching adapter in the catalog
   - If all BRD services are covered, states that explicitly

   **Section 5: Field Mapping Summary**
   - Per integration: total fields mapped vs total required, computed/transformed fields, fields with special notes (encryption, format conversion)

   **Section 6: Overall Assessment**
   - How complete is the integration coverage
   - Critical gaps the reviewer should address
   - Confidence level: High / Medium / Low

5. **Save Report** — The markdown output is saved as `clients/{client_id}/reasoning_report.md`.

6. **Audit Event** — Records: number of integrations analyzed, missing fields flagged, unmatched services found.

**Progress:** 65% at start, 75% on completion.

---

## Slide 12: Stage 5 — Cleaner Agent (Detailed)

### Heading: Stage 5 — Production Config Cleaner

**Purpose:** Sanitize the config by removing pipeline annotations, validating structure, and ensuring no secrets leak into the config JSON.

**How It Works — Step by Step:**

1. **Load Current Config** — Reads the latest config version.

2. **LLM Cleaning (1 LLM call)** — The config is sent to Gemini with a system prompt that instructs it to:
   - Remove all keys ending in `_reason` (e.g., `_adapter_reason`, `_version_reason`, `_mapping_reason`) — these are pipeline annotations not meant for production
   - Scan for any string that looks like an actual API key (long alphanumeric strings, Bearer tokens, base64 tokens) and replace with `$ENV_VAR_NAME` references
   - Remove placeholder strings like "TBD", "to be filled", empty strings in metadata
   - Ensure every `credential_env_vars` entry uses `$VARIABLE_NAME` format
   - Clean up any LLM artifacts that may have leaked from prompts
   - Preserve ALL integrations, hooks, field mappings, and transformation rules — do NOT remove any business data
   - Do NOT change endpoint URLs, version selections, or business logic

3. **Structure Validation (Code):**
   - If the LLM accidentally removed `integrations` or `metadata`, they are restored from the pre-cleaning config
   - For each integration, if hooks were dropped during cleaning (known LLM behavior), they are restored from the pre-cleaning version

4. **Post-Processing (Code):**
   - Scans for Bearer tokens and long hex strings using regex patterns
   - Ensures `pipeline_run.overall_status` field exists in metadata

5. **Hard Programmatic Guarantee — `strip_reason_fields()` (Code):**
   - Even after the LLM cleaning, the code runs a recursive function that traverses the entire config and deletes ANY key ending in `_reason` or named `mapping_reason`
   - This is a belt-and-suspenders approach: the LLM should remove them, but the code guarantees it

6. **Save Cleaned Config** — Saved back to the current config version file.

7. **Audit Event** — Records the size delta (characters removed/added) and confirms integrations count preserved.

**Progress:** 80% at start, 85% on completion.

---

## Slide 13: Stage 6 — Human-in-the-Loop Review (Detailed)

### Heading: Stage 6 — Human-in-the-Loop Review & Corrector Agent

**Purpose:** Pause the pipeline for mandatory human review before simulation. Ensure a human validates the AI-generated config.

**How It Works — Step by Step:**

1. **Pipeline Pause:**
   - The orchestrator calls `pause_for_review()` which sets config status to `awaiting_review` and `human_review_status` to `pending`.
   - Config is saved. Frontend polling detects the status change and displays the review UI.
   - Progress is set to 90%.

2. **Review Dashboard:**
   - The dashboard displays the full config JSON in a viewer.
   - Alongside it, the reasoning report (from Stage 4) is rendered as formatted markdown, so the reviewer can read WHY each decision was made.
   - The reviewer has two options: **Approve** or **Request Changes**.

3. **Path A — Approve:**
   - Reviewer clicks "Approve".
   - Backend calls `approve_config()`:
     - Sets `overall_status` to `"approved"`, `human_review_status` to `"approved"`, `status` to `"approved"`
     - Records the reviewer identity
     - Saves config
   - Stage 7 (Simulation) is automatically triggered as a background task.
   - Audit event recorded: "Config vN approved".

4. **Path B — Request Changes:**
   - Reviewer types natural-language feedback (e.g., "Remove the Twilio integration and change CIBIL timeout to 10000ms").
   - Backend calls `request_changes()`:
     - Checks correction iteration count. If already at maximum (3 iterations), config status is set to `"escalated"` and no further corrections are allowed. An audit event records the escalation.
     - If iterations remain, the **Corrector Agent** is invoked:
       - The current config JSON + reviewer's feedback text are sent to Gemini.
       - The LLM applies the requested changes precisely while preserving all structure and `$ENV_VAR` credential references.
       - The response is validated (integrations and metadata must be present).
       - `correction_iterations` counter is incremented.
       - Config is saved as a NEW version (e.g., `config_v2.json`), not overwriting the previous version.
       - Config status returns to `"awaiting_review"` for another round of review.
     - Audit event recorded: "Correction N applied, saved as vN".
   - The reviewer can review the updated config and approve or request more changes (up to 3 total).

**Progress:** 90% (remains here until approved).

---

## Slide 14: Stage 7 — Simulation & Testing (Detailed)

### Heading: Stage 7 — Simulation & Testing Framework

**Purpose:** Test the approved config against mock API responses and generate a confidence score.

**How It Works — Step by Step:**

1. **Load Approved Config** — Reads the latest (approved) config version.

2. **Integration-by-Integration Simulation:**
   For each integration in the config's `integrations[]` array:
   - **Load Mock Response:**
     - Looks for a mock file at `mocks/{adapter_id}/{version}_success.json` (e.g., `mocks/cibil/v2_success.json`)
     - Tries fallback paths: without `v` prefix, any available mock in the adapter directory
     - If no mock exists, generates a generic mock with `status: "simulated"` and `response_code: 200`
   - **Field Mapping Coverage Check:**
     - Counts the number of field mappings for this integration
     - Lists all response fields from the mock response
   - **Records Simulation Result:**
     - `integration_id`, `adapter_id`, `version`
     - `mock_response` — the full mock response data
     - `mapped_fields_count` — number of field mappings
     - `transformation_rules_count` — number of transformation rules
     - `response_fields` — fields present in the mock response
     - `mock_available` — whether a real mock file was found (vs generic)

3. **Report Generation (1 LLM call):**
   - The full config + all simulation results are sent to Gemini.
   - The LLM generates a structured JSON simulation report with:
     - `report_id` — unique identifier
     - `generated_at` — UTC timestamp
     - `overall_confidence_score` — 0-100, calculated as (correctly_resolved / total_required) x 100, with -10 penalty per mandatory field failure
     - `overall_passed` — boolean
     - `total_integrations_tested`, `passed_count`, `failed_count`
     - `human_readable_summary` — a clear paragraph summarizing results
     - `recommended_actions[]` — list of actions to take
     - `integration_results[]` — per-integration: confidence_score, fields_mapped_correctly, total_required_fields, type_mismatches, missing_mandatory_fields, transformation_rule_failures, notes

4. **Save Report:**
   - Report is saved as a timestamped file: `simulation_reports/simulation_report_YYYYMMDD_HHMMSS.json`
   - Config is updated: `simulation_report` section is filled, `overall_status` set to `"completed"`, `status` set to `"production-ready"`
   - Config is saved.

5. **Audit Event** — Records: confidence score, passed count, failed count.

**Detailed Scenario Testing (On-Demand via Dashboard):**
In addition to the pipeline simulation, the dashboard offers on-demand detailed scenario testing with 6 fault-injection scenarios per integration:
1. **Normal Success** — 200 OK with valid response, all field mappings validated
2. **API Failure Handling** — Injected 500 error, verifies retry policy triggers correctly
3. **Timeout Handling** — Injected timeout at configured limit, verifies circuit breaker engagement
4. **Missing Field Validation** — Removes required fields, verifies 422 validation error with correct field identification
5. **Fallback Testing** — Primary adapter fails, verifies fallback adapter succeeds (if configured)
6. **Version Comparison** — Tests all available versions of the adapter for compatibility

**Fidelity Score** = (scenarios matched / total scenarios) x 100

**Progress:** 92% at start, 100% on completion.

---

## Slide 15: Integration Registry & Adapter Catalog

### Heading: Pre-Built Adapter & Hook Registry

**Adapter Catalog (12 Adapters):**
Each adapter is a versioned JSON file with:
- `adapter_name`, `category`, `base_url`
- `versions[]` — each with version ID, endpoint, status (stable/latest/deprecated), `deprecated` flag, `sunset_date`, `maturity_score`
- `auth` — authentication type, required credentials, token endpoint
- `required_fields[]` / `optional_fields[]` — API schema
- `rate_limits`, `timeout_ms`, `retry_policy`
- `sandbox_url`, `fallback_adapter`

| Adapter | Category | Versions |
|---|---|---|
| CIBIL | Credit Bureau | v2 (stable), v3 (latest) |
| Experian | Credit Bureau | v1, v2, v3 |
| Karza | KYC/Identity | v2, v3 |
| DigiLocker | Document Verification | v1, v2 |
| GST | Tax/Compliance | v1, v2 |
| Perfios | Banking/Financial | v2, v3 |
| Razorpay | Payment Gateway | v1, v2 |
| PennyDrop | Bank Verification | v1, v2 |
| Twilio | Messaging/OTP | v1, v2 |
| RiskGuard | Fraud Detection | v1, v2 |
| Stripe | Payment Gateway | v1, v2 |

**Hook Catalog (14 Hooks):**
Lifecycle hooks that attach to integrations:

| Hook | Type | Purpose |
|---|---|---|
| `credential_resolve_hook` | pre_request | Resolve API keys from .env vault |
| `pre_auth_hook` | pre_request | OAuth token refresh, session setup |
| `field_encryption_hook` | pre_request | Encrypt PII (PAN, Aadhaar) before send |
| `pre_validation_hook` | pre_request | Validate request payload schema |
| `post_schema_validation_hook` | post_response | Validate response against expected schema |
| `post_transform_hook` | post_response | Transform API response to internal format |
| `retry_hook` | error_handler | Exponential backoff retry on failures |
| `on_failure_alert_hook` | error_handler | Alert on integration failure |
| `audit_emit_hook` | lifecycle | Emit audit event on every API call |
| `rate_limit_guard_hook` | pre_request | Enforce rate limits before API calls |
| `simulation_intercept_hook` | simulation | Intercept calls for simulation mode |
| `version_compatibility_hook` | pre_request | Validate API version compatibility |
| `logging_hook` | lifecycle | Structured logging |

**Master Index Files:**
Both catalogs have a `master_index.json` that indexes all adapters/hooks by ID, name, category, versions, and file path — enabling fast lookup during Stage 3 matching.

**One-Click Catalog Extension:**
New adapters and hooks can be added via a simple JSON file upload through the dashboard or API (`POST /api/catalogs/adapters/upload` and `POST /api/catalogs/hooks/upload`). The master index is automatically updated.

---

## Slide 16: Multi-Tenant Architecture & Security

### Heading: Multi-Tenant Isolation & Security

**Tenant Isolation:**
- Each client project gets a completely isolated folder: `clients/client_{uuid}/`
- Contains: `.env` (credential vault), `configs/`, `input_documents/`, `simulation_reports/`, `diffs/`, `audit/`
- Zero cross-tenant data access — all API endpoints are scoped by `client_id`.

**Role-Based Access Control (3 Roles):**

| Feature | Admin | Standard | Client |
|---|---|---|---|
| View All Projects | Yes | Yes | No (own only) |
| Create Projects | Yes | Yes | No |
| Upload Documents | Yes | Yes | No |
| Run Pipeline | Yes | Yes | No |
| Review & Approve Config | Yes | Yes | No |
| Edit Config JSON | Yes | Yes | No |
| View/Edit Credentials | Yes | No | Yes (own only) |
| Upload Adapters/Hooks | Yes | No | No |
| View Audit Log | Yes | Yes | Yes (own only) |
| Run Simulation | Yes | Yes | No |
| Download Config/Reports | Yes | Yes | Yes (own only) |

**Credential Security:**
- API keys and secrets are stored in per-client `.env` files — NEVER in config JSONs.
- Config files use `$ENV_VAR_NAME` references (e.g., `$CIBIL_API_KEY`, `$KARZA_OAUTH_SECRET`).
- The pipeline's Cleaner Agent (Stage 5) actively scans for leaked credentials and replaces them with `$ENV_VAR` references.
- The `.env` file is auto-populated with empty stubs for all `$ENV_VAR` references found in configs.
- Admin and Client roles can view and edit credentials through the dashboard — Client access is restricted to their own project only.

**Audit Trail:**
- Every action is logged: timestamp (UTC ISO 8601), pipeline stage, action description, responsible agent (LLM model / user / system), responsible party (human / system), SHA-256 input/output hashes, and details.
- Stored per-client in `audit/audit_log.json`.
- Provides full traceability for compliance and governance.

---

## Slide 17: Business Impact

### Heading: Business Impact & ROI

**Implementation Cycle Time:**
- **Before:** 4-8 weeks per client onboarding
- **After:** Minutes (pipeline execution) + human review time
- **Reduction: ~95%**

**Configuration Defect Rate:**
- **Before:** 30-40% due to manual errors
- **After:** Near-zero — AI extraction + human review + simulation validation
- **Reduction: ~90%+**

**Client Onboarding Velocity:**
- **Before:** Serial onboarding — one client's config at a time
- **After:** Parallel onboarding — pipeline runs independently per client via background tasks, batch processing endpoint supports multiple simultaneous runs
- **Improvement: 5-10x faster**

**Integration Governance:**
- **Before:** No audit trail, no version history, no diff tracking
- **After:** Full SHA-256 hashed audit log, versioned configs, structured diffs, reasoning reports
- **Result:** Complete compliance and change traceability

**Developer Productivity:**
- **Before:** Senior engineers spend weeks on config work
- **After:** Engineers focus on business logic; AI handles boilerplate configuration
- **Result:** Engineer time redirected to high-value work

**Key Metrics from Prototype:**
- 12 pre-built adapters across 8 categories (bureau, KYC, payment, banking, GST, fraud, messaging, document)
- 14 lifecycle hooks (security, retry, audit, simulation)
- ~9 LLM calls per pipeline run with full observability via LangSmith
- Structured simulation with 6-scenario testing per integration
- Confidence scoring on every pipeline run

---

## Slide 18: Extra Features

### Heading: Additional Capabilities

**1. Upload Updated Documents & Re-Run Pipeline**
- After initial pipeline completion, users can upload revised BRD/SOW documents via the dashboard.
- The system archives old documents, creates a new config version (v2, v3, etc.), and re-runs the full 7-stage pipeline from scratch.
- New simulation reports are generated for the updated config.
- Full history is preserved — old configs, documents, and reports are never deleted.

**2. One-Click Adapter & Hook Upload**
- New adapters can be added to the catalog by simply uploading a JSON file via the dashboard or API.
- The master index is automatically updated — no manual index editing required.
- Same for hooks — upload the hook JSON and it's immediately available for pipeline matching.

**3. Version Migration Engine**
- Any integration can be migrated to a newer API version with a single API call.
- If no target version is specified, the engine auto-picks the latest non-deprecated stable version.
- A new config version is created, and audit trail records the migration.

**4. In-Dashboard Config Editor**
- The config JSON can be manually edited directly in the dashboard.
- Changes are saved via API and fully audited (who changed what, when).

**5. Credential Management Dashboard**
- Admin and Client roles can view and edit credential key-value pairs via the dashboard.
- Credentials are auto-grouped by adapter prefix (CIBIL, KARZA, PERFIOS, etc.).
- Comments and structure in .env files are preserved on updates.
- Client access is scoped to their own project only.

**6. Config & Document Download**
- Any config version or uploaded document can be downloaded as a file directly from the dashboard.

**7. LLM Observability (LangSmith)**
- Every LLM call is decorated with `@traceable(run_type="llm")` for full tracing.
- Enables debugging, latency monitoring, and cost tracking for all AI operations.

**8. Reasoning Report Viewer**
- The markdown reasoning report (Stage 4) is rendered directly in the dashboard using react-markdown with GitHub Flavored Markdown support.
- Reviewers can read the full explanation of why each adapter, version, and field mapping was chosen.

**9. Batch Pipeline Processing**
- Backend supports triggering pipelines for multiple client IDs simultaneously.
- Each pipeline runs as an independent background task.

**10. Auto-Generated Credential Stubs**
- When a config is saved, the system scans for all `$ENV_VAR` references and automatically creates empty entries in the client's `.env` file.
- This ensures no credential reference is ever missed.

---

## Slide 19: Future Plans — Prototype to Product

### Heading: Roadmap — From Prototype to Production Product

**Phase 1: Core Infrastructure Hardening**
- **Database Integration** — Migrate from file-based storage to PostgreSQL/MongoDB for scalability, concurrent access, ACID transactions, and production-grade querying. Config versions, audit logs, and simulation reports would be stored as structured records.
- **Authentication & Authorization** — Replace the current localStorage-based role system with a proper authentication layer (OAuth 2.0 / JWT tokens) backed by an identity provider (Auth0, Firebase Auth, or custom SSO). Enforce role-based access at the API layer, not just the frontend.
- **Containerization & Deployment** — Dockerize the backend and frontend. Provide docker-compose for single-node deployment and Kubernetes manifests (Helm charts) for cloud-native scaling. CI/CD pipeline with automated testing.

**Phase 2: Pipeline Intelligence Enhancements**
- **Real API Sandbox Testing** — Move from mock-response simulation to actual sandbox API calls. Integrate with adapter sandbox environments to validate configs against real API endpoints in a safe testing mode.
- **Multi-LLM Support** — Support pluggable LLM backends (OpenAI GPT, Anthropic Claude, open-source models via Ollama) beyond Gemini. Allow organizations to choose their preferred LLM provider or use on-premise models for data privacy.
- **Learning from Corrections** — Build a feedback loop: when a human reviewer requests changes at Stage 6, store the correction patterns. Over time, the pipeline learns from past corrections to reduce future human intervention. Fine-tune prompts based on historical review feedback.
- **Confidence-Based Auto-Approval** — If the simulation confidence score exceeds a configurable threshold (e.g., 95%), allow automatic approval without human review for low-risk configs.

**Phase 3: Enterprise Features**
- **Multi-Organization Tenancy** — Support multiple organizations, each with their own users, roles, adapter catalogs, and projects. Organization-level admin, billing, and usage analytics.
- **Custom Adapter SDK** — Provide a developer SDK and CLI for building custom adapters. Include schema validation, test harness, and one-click publishing to the organization's private catalog.
- **Workflow Engine** — Allow organizations to customize the pipeline stages — add custom stages, skip stages, or reorder them based on their governance requirements.
- **Notification System** — Email/Slack/webhook notifications when pipeline completes, review is needed, or config is escalated.
- **Analytics Dashboard** — Track: pipeline success rates, average completion time, most-used adapters, common correction patterns, LLM cost per pipeline run.

**Phase 4: Scale & Ecosystem**
- **Public Adapter Marketplace** — Community-contributed adapter catalog where organizations can publish and discover adapters, similar to a package registry.
- **API Gateway Integration** — Auto-provision API gateway routes (Kong, AWS API Gateway) based on the generated config — direct path from config to live routing.
- **Compliance Certifications** — SOC 2, ISO 27001, GDPR readiness with built-in data retention policies, right-to-delete, and encryption at rest.

---

## Slide 20: Closing

### Heading: FinSpark — The Future of Integration Configuration

**What We Built:**
An end-to-end AI-powered Integration Orchestration Engine that transforms requirement documents into production-ready, fully validated integration configurations — reducing weeks of manual work to minutes.

**The Answer to the Big Question:**
*"Can you transform requirement documents into production-ready integration configurations and eliminate manual integration bottlenecks?"*

**Yes.** FinSpark does exactly this — with:
- 7-stage AI pipeline from document to production config
- Human-in-the-loop review for safety
- Automatic deprecation handling and version migration
- Full audit trail for compliance
- Multi-tenant isolation and role-based security
- Simulation testing with confidence scoring
- One-click extensibility via adapter/hook uploads

**Thank You!**

*Questions?*
