# Integration Reasoning Report

## 1. Adapter Selection Rationale

| Integration | Adapter ID | Rationale |
| :--- | :--- | :--- |
| **Karza KYC** | `karza` | Matches the requested provider 'Karza Technologies' exactly; supports required KYC category and functionality. |
| **TransUnion CIBIL** | `cibil` | Exact match for 'TransUnion CIBIL'; highest semantic similarity score among candidates. |
| **Perfios AA** | `perfios` | Matches the requested provider 'Perfios' for banking/financial analysis. |

## 2. Version Selection & Deprecation Notices

*   **Karza KYC (v2):** Selected as the stable version supporting required liveness checks and facial match features.
*   **TransUnion CIBIL (v3):** Selected as the latest stable version with advanced insights; avoids deprecated v1 and legacy v2 report formats.
*   **Perfios AA (v2):** Selected as the current stable version for the Account Aggregator framework.

⚠️ **Deprecation Status:** All selected versions are currently stable and non-deprecated. Sunset dates are set for 2027-2028, providing sufficient runway for future migration.

## 3. Missing Required Fields

The following fields are required by the respective APIs but were not found in the provided BRD input data:

*   **TransUnion CIBIL:**
    *   `mobile_number`: Required by the adapter for identity verification but missing from the BRD input schema.
*   **Perfios Account Aggregator:**
    *   `account_number`: Required by the API to scope financial data; missing from BRD.
    *   `ifsc_code`: Required by the API for bank branch identification; missing from BRD.

⚠️ **Warning:** These fields are mandatory for successful API execution. The pipeline will fail at runtime unless these fields are added to the application intake form or derived via business logic.

## 4. Unmatched APIs / Services

The following services were requested in the BRD but are missing from the current integration configuration:

*   **RiskGuard Analytics Engine:** Requested in Section 3.2.4 for real-time fraud scoring. No adapter was found in the configuration.
*   **Twilio SMS:** Requested in Section 3.2.5 for transactional notifications. No adapter was found in the configuration.

## 5. Field Mapping Summary

| Integration | Mapped Fields | Missing Fields | Notes |
| :--- | :--- | :--- | :--- |
| **Karza KYC** | 5 | 0 | Includes AES-256 encryption for PII (PAN, Aadhaar). |
| **TransUnion CIBIL** | 4 | 1 | Includes format transformation (DOB) and encryption (PAN). |
| **Perfios AA** | 4 | 2 | Direct mapping for consent and date ranges. |

*   **Transformations:** All PII fields (PAN, Aadhaar, DOB) are subject to `field_encryption_hook` (AES-256-GCM) and format normalization (ISO 8601) as per security requirements.

## 6. Overall Assessment

*   **Coverage:** Partial. While the core KYC, Bureau, and Banking integrations are configured, the Fraud Detection (RiskGuard) and Communication (Twilio) modules are missing.
*   **Critical Gaps:** The absence of the RiskGuard adapter is a critical gap, as it is a mandatory requirement for the real-time credit decisioning engine. Additionally, the missing fields for CIBIL and Perfios must be addressed to ensure successful API calls.
*   **Confidence Level:** **Medium**. The core logic and security hooks are well-defined, but the integration suite is incomplete relative to the BRD requirements.

**Recommendation:** Prioritize the addition of RiskGuard and Twilio adapters and update the intake schema to include the missing mobile, account, and IFSC fields.