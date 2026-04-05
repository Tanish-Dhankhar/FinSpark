# Integration Reasoning Report

## 1. Adapter Selection Rationale
The pipeline successfully matched all five required services identified in the BRD to specific adapters within the integration catalog.

*   **Karza KYC Provider (`karza`):** Selected for identity verification (Aadhaar/PAN) as per BRD Section 3.2.1.
*   **TransUnion CIBIL Bureau (`cibil`):** Selected for credit assessment as per BRD Section 3.2.2.
*   **Perfios Account Aggregator (`perfios`):** Selected for financial verification via the AA framework as per BRD Section 3.2.3.
*   **RiskGuard Analytics Engine (`riskguard`):** Selected for real-time fraud scoring as per BRD Section 3.2.4.
*   **Twilio SMS (`twilio`):** Selected for transactional applicant communication as per BRD Section 3.2.5.

## 2. Version Selection & Deprecation Notices
The system has defaulted to "Latest Stable" or "Latest Non-Deprecated Stable" versions for all adapters, adhering to the note in BRD Section 3.1 which states that NovaCred does not prescribe specific minor versions.

*   **All Adapters:** Versions are set to `latest_stable`. No specific deprecation notices are currently active for these versions. The pipeline is configured to monitor for sunset timelines and trigger re-configuration if a version becomes deprecated.

## 3. Missing Required Fields
The following fields were identified as required by the respective APIs but could not be mapped to the provided BRD data model:

| Integration | Missing API Field | Reason |
| :--- | :--- | :--- |
| **Perfios** | `consent_artifact` | No corresponding data point in the BRD; required for AA consent validation. |
| **Twilio** | `to` | The destination phone number is not explicitly mapped in the current schema. |

⚠️ **Warning:** These fields are critical for successful API execution. They must be provided at runtime via the application context or a dynamic lookup service.

## 4. Unmatched APIs / Services
All services mentioned in the BRD (Karza, CIBIL, Perfios, RiskGuard, and Twilio) have been successfully mapped to an integration adapter. No services were left unaddressed.

## 5. Field Mapping Summary

| Integration | Mapped Fields | Total Required | Notes |
| :--- | :--- | :--- | :--- |
| **Karza** | 3 | 3 | Includes AES-256 encryption for `aadhaar_uid` and `pan_id`. |
| **CIBIL** | 4 | 4 | Includes date format conversion (DD-MM-YYYY to ISO 8601). |
| **Perfios** | 5 | 6 | 1 field missing (`consent_artifact`). |
| **RiskGuard** | 6 | 6 | Direct mapping for fraud scoring parameters. |
| **Twilio** | 3 | 4 | 1 field missing (`to`). |

*   **Transformations:** The pipeline applies AES-256 encryption to PII fields for Karza and CIBIL to ensure compliance with RBI Digital Lending Guidelines.
*   **Formatting:** Date fields for CIBIL are automatically normalized to ISO 8601.

## 6. Overall Assessment
*   **Integration Coverage:** High. All mandatory services are accounted for with appropriate hooks for retries, authentication, and auditing.
*   **Critical Gaps:** The missing `consent_artifact` for Perfios and `to` (destination phone) for Twilio are the only blockers for full automation. These must be addressed by the implementation team before moving to production.
*   **Confidence Level:** **High**. The orchestration logic (parallel execution for RiskGuard/Karza and CIBIL/Perfios) aligns perfectly with the BRD requirements. The pipeline is ready for deployment pending the resolution of the two missing field mappings.