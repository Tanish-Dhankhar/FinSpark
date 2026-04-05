# Integration Reasoning Report

## 1. Adapter Selection Rationale
The pipeline successfully matched all required services identified in the NovaCred BRD to the internal integration catalog:

*   **Karza KYC Provider (`int_karza_001`):** Direct match for Karza KYC provider in catalog.
*   **TransUnion CIBIL Bureau (`int_cibil_001`):** Best category match for credit bureau; highest maturity score.
*   **Perfios Account Aggregator (`int_perfios_001`):** Matches Perfios Account Aggregator service.
*   **RiskGuard Analytics Engine (`int_riskguard_001`):** Matches internal RiskGuard analytics engine.
*   **Twilio SMS (`int_twilio_001`):** Matches Twilio messaging service.

## 2. Version Selection & Deprecation Notices
Versions were selected based on stability, feature availability, and support lifecycles:

*   **Karza (v2):** Selected as the current stable version with liveliness check support.
*   **CIBIL (v3):** Selected as it provides advanced insights and is the latest stable version.
*   **Perfios (v2):** Selected for native Account Aggregator FIP framework support.
*   **RiskGuard (v2):** Selected as it is the stable version; v3 is currently in beta.
*   **Twilio (v3):** Selected for latest features and extended support lifecycle.

⚠️ **Deprecation Status:** No selected versions are currently deprecated. All sunset dates (where applicable) extend beyond the immediate implementation horizon (2027–2031).

## 3. Missing Required Fields
The following fields are required by the provider APIs but lack corresponding data in the provided BRD:

| Integration | Missing Field | Reason |
| :--- | :--- | :--- |
| **Perfios** | `consent_artifact` | Required API field has no corresponding data in the BRD. |
| **Twilio** | `to` | Required API field (destination phone) has no corresponding data in the BRD. |

⚠️ **Warning:** These fields are mandatory for successful API execution. They must be provided at runtime via the application context or a dynamic lookup service.

## 4. Unmatched APIs / Services
All services mentioned in the BRD (Karza, CIBIL, Perfios, RiskGuard, and Twilio) have been successfully mapped to an adapter in the configuration. No services are missing.

## 5. Field Mapping Summary

| Integration | Mapped Fields | Transformation/Notes |
| :--- | :--- | :--- |
| **Karza** | 5/5 | AES-256 encryption applied to `aadhaar_uid` and `pan_id`. |
| **CIBIL** | 5/5 | Format conversion (DD-MM-YYYY to ISO 8601) for DOB; AES-256 encryption for `pan_id`. |
| **Perfios** | 5/6 | 1 field missing (`consent_artifact`). |
| **RiskGuard** | 6/6 | AES-256 encryption applied to `pan_id`. |
| **Twilio** | 3/4 | 1 field missing (`to`). |

## 6. Overall Assessment
*   **Coverage:** High. All business-critical integrations are accounted for and mapped to stable API versions.
*   **Critical Gaps:** The pipeline is missing runtime-specific data for `consent_artifact` (Perfios) and `to` (Twilio). These are critical for the workflow to function.
*   **Confidence Level:** **High**. The logic correctly identifies the need for encryption on PII and handles the parallel/sequential orchestration requirements defined in the BRD. The missing fields are expected to be resolved at the application layer during the execution phase.