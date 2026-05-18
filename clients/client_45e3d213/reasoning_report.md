# Integration Reasoning Report

## 1. Adapter Selection Rationale
*   **Karza KYC (`karza-kyc-001`)**: Selected based on high semantic similarity to the "KYC" category and the client's requirement for Aadhaar/PAN verification.
*   **TransUnion CIBIL (`transunion_cibil_integration`)**: Selected as the industry-standard adapter for Indian credit bureau reporting, fulfilling the BRD requirement for creditworthiness assessment.
*   **Twilio SMS (`twilio-sms-integration`)**: Selected to fulfill the requirement for automated SMS notifications at each processing milestone.

## 2. Version Selection & Deprecation Notices
*   **Karza KYC (v2)**: Current stable version; supports required liveness and facial matching features.
*   **TransUnion CIBIL (v3)**: Latest stable version; provides advanced insights and is not deprecated.
*   **Twilio SMS (v3)**: Selected as the latest stable version. v1 was explicitly excluded due to deprecation.

| Integration | Selected Version | Status | Sunset Date |
| :--- | :--- | :--- | :--- |
| Karza KYC | v2 | Stable | 2028-12-31 |
| TransUnion CIBIL | v3 | Stable | 2027-12-31 |
| Twilio SMS | v3 | Stable | 2031-12-31 |

## 3. Missing Required Fields

| Integration | Missing Field | API Requirement | Suggested Source |
| :--- | :--- | :--- | :--- |
| Karza KYC | aadhaar_number | Identity verification | Applicant Intake Form |
| Karza KYC | pan_number | Identity verification | Applicant Intake Form |
| TransUnion CIBIL | pan_number | Identity matching | Applicant Intake Form |
| TransUnion CIBIL | full_name | Identity matching | Applicant Intake Form |
| TransUnion CIBIL | date_of_birth | Identity matching | Applicant Intake Form |
| TransUnion CIBIL | mobile_number | Identity matching | Applicant Intake Form |

> ⚠️ **Warning**: These fields must be resolved before production deployment. The missing fields are critical for identity matching and KYC compliance. These should be mapped to the `Applicant Intake Form` data object captured at the start of the loan origination flow.

## 4. Unmatched APIs / Services
The BRD mentions a requirement for **Bank Account Verification** (verifying account validity and name matching). There is currently no integration entry for a Bank Account Verification service (e.g., Penny Drop or API-based validation).

*   **Recommendation**: A new adapter JSON should be created in `backend/catalogs/adapters/` for a service like *Cashfree* or *RazorpayX* (common in the Indian lending ecosystem) to handle bank account validation.

## 5. Field Mapping Summary

| Integration | Total Fields | Mapped (Direct/Rename) | Missing |
| :--- | :--- | :--- | :--- |
| Karza KYC | 3 | 1 | 2 |
| TransUnion CIBIL | 5 | 1 | 4 |
| Twilio SMS | 4 | 4 | 0 |

*   **PII Handling**: Aadhaar numbers and PAN numbers are identified as PII. Ensure the pipeline configuration applies masking transformations for these fields in all logs and audit trails as per Section 5 of the BRD.
*   **Format Conversions**: The `consent_timestamp` for CIBIL must be validated against ISO 8601 format requirements.

## 6. Overall Assessment

**Coverage**: 3/4 integrations matched (Bank Account Verification service is missing).
**Confidence**: Medium — The core KYC and Credit services are correctly identified, but the missing Bank Account Verification service and the reliance on runtime injection for PII fields require immediate attention.

**Critical Actions Required (⚠️ must fix before production):**
1. **Implement Bank Account Verification**: Add an adapter for bank account validation to satisfy the BRD requirement in Section 2.
2. **Resolve Mapping Gaps**: Map the missing identity fields (Aadhaar, PAN, Name, DOB, Mobile) from the intake form to the respective API fields.
3. **Security Compliance**: Ensure the `account_sid` for Twilio is fetched from a secure vault and not hardcoded in the configuration.

**Recommended Actions:**
*   Implement a retry logic wrapper for the Bank Account Verification service as requested in the BRD (up to 2 re-attempts).
*   Configure the pipeline to mask Aadhaar numbers in all logging middleware.