# Integration Reasoning Report

## 1. Adapter Selection Rationale

The integration pipeline processed three service requests identified in the BRD. All three have been successfully mapped to stable adapters.

| Integration ID | Service Name | Adapter ID | Rationale |
| :--- | :--- | :--- | :--- |
| `karza_kyc_001` | Karza KYC | `karza` | Explicitly requested in BRD for identity verification. |
| `transunion_cibil_001` | TransUnion CIBIL | `cibil` | Industry standard for credit bureau checks; matches repayment risk assessment requirement. |
| `bank_account_verification_001` | Bank Account Verification | `pennydrop` | Standard for IMPS-based bank validity verification. |

⚠️ **ID FORMAT WARNING**
*   `karza_kyc_001`: Compliant.
*   `transunion_cibil_001`: Compliant.
*   `bank_account_verification_001`: Compliant.
*   *Note*: All provided `integration_id` values follow the required `snake_case_with_suffix_001` format.

## 2. Version Selection & Deprecation Notices

*   **Karza KYC (v2)**: Selected as the current stable version. v1 is deprecated; v2 is fully supported until 2028-12-31.
*   **TransUnion CIBIL (v3)**: Selected as the latest stable version. No deprecation notices; sunset date is 2027-12-31.
*   **Bank Account Verification (v1)**: Selected as the current stable version. No deprecation notices; sunset date is 2028-06-30.

## 3. Missing Required Fields

No fields were marked with `mapping_type: "missing"` in the provided configuration. All required API fields are currently mapped to either global BRD applicant data or system-computed constants.

⚠️ **Status**: No missing field resolutions required for current configuration.

## 4. Unmatched APIs / Services

Cross-referencing the BRD against the integration config reveals the following gap:

*   **Twilio SMS**: The BRD explicitly requires SMS notifications for application receipt, verification completion, credit decisions, and loan approval. This service is currently **unmatched** in the integration config.
    *   **Recommendation**: Create a new adapter entry in `backend/catalogs/adapters/` for `twilio_sms`. The configuration must include fields for `account_sid`, `from`, `to`, and `body` as specified in section 3.2 of the BRD.

## 5. Field Mapping Summary

| Integration | Total Mappings | PII Fields | Format Conversion |
| :--- | :--- | :--- | :--- |
| `karza_kyc_001` | 6 mapped, 0 missing | `aadhaar_number`, `pan_number`, `full_name`, `mobile_number` | None |
| `transunion_cibil_001` | 8 mapped, 0 missing | `pan_number`, `full_name`, `mobile_number`, `email`, `address` | `consent_timestamp` (ISO 8601) |
| `bank_account_verification_001` | 4 mapped, 0 missing | `account_holder_name` | None |

## 6. Overall Assessment

**Coverage**: 3/4 integrations matched. 1 service (Twilio SMS) is missing from the configuration.
**Confidence**: Medium. While the core financial and identity services are correctly mapped, the communication layer (SMS) is missing, which is a functional requirement for the "end-to-end" processing described in the BRD.

**Critical Actions Required** (⚠️ must fix before production):
1.  **Implement Twilio Integration**: Add the `twilio_sms` adapter to the integration pipeline to satisfy the mandatory SMS notification requirements defined in Section 2 and Section 3.2 of the BRD.
2.  **Security Compliance**: Ensure the `account_sid` for the Twilio integration is retrieved from the secure vault at runtime and is not hardcoded in the configuration.

**Recommended Actions** (nice to have):
*   Implement a retry-logic wrapper for the `pennydrop` integration to handle the "up to 2 re-attempts" requirement specified in Section 4 of the BRD.
*   Verify that the `consent_timestamp` format for CIBIL is strictly enforced as UTC ISO 8601 to prevent downstream rejection.