# Integration Reasoning Report

## 1. Adapter Selection Rationale

| Integration | Adapter ID | Rationale |
| :--- | :--- | :--- |
| **Karza KYC** | `karza` | Matched based on provider requirements for Aadhaar/PAN verification. |
| **TransUnion CIBIL** | `cibil` | Matched based on bureau category requirements for credit assessment. |
| **Razorpay** | `razorpay` | Matched for payment disbursal functionality. |
| **Aarogya Health API** | `Aarogya_Health_API` | Custom adapter initialized to support NDHM framework requirements. |
| **Twilio SMS** | `twilio` | Matched for automated applicant notification requirements. |

## 2. Version Selection & Deprecation Notices

*   **Karza (v2):** Selected as it aligns with the current stable production API for identity verification.
*   **CIBIL (v3):** Selected as the current standard for consumer credit scoring.
*   **Razorpay (v1):** Selected for compatibility with existing order creation endpoints.
*   **Aarogya Health API (v1.2):** Selected to match the specific version requested in the BRD.
*   **Twilio (v2):** Selected as the stable version for messaging; note that the BRD referenced `v2010-04-01`, which is mapped to the current `v2` adapter.

⚠️ **Deprecation Warning:** While no immediate sunset dates are active, ensure that the `v1.2` Aarogya API remains compliant with evolving NDHM standards.

## 3. Missing Required Fields

*   **Aarogya Health API (`int_aarogya_004`):**
    *   **Field:** `consent_token`
    *   **Reason:** The BRD specifies that this is a session-scoped, patient-level token generated at runtime. It is not available in the static input data.
    *   ⚠️ **Warning:** This field must be injected into the pipeline at runtime via the `pre-call` hook or session manager.

## 4. Unmatched APIs / Services

All services requested in the BRD (Karza, CIBIL, Razorpay, Aarogya Health API, and Twilio) have been successfully mapped to adapters in the configuration. No additional services were identified as missing.

## 5. Field Mapping Summary

| Integration | Mapped Fields | Transformation/Notes |
| :--- | :--- | :--- |
| **Karza** | 6/6 | Aadhaar encryption; DOB format conversion (DD/MM/YYYY to YYYY-MM-DD). |
| **CIBIL** | 4/4 | DOB format conversion (DD/MM/YYYY to ISO 8601). |
| **Razorpay** | 5/5 | Computed field: Loan Amount (INR to paise). |
| **Aarogya** | 7/8 | Aadhaar masking/encryption. `consent_token` is missing. |
| **Twilio** | 4/4 | Direct mapping for SMS delivery. |

## 6. Overall Assessment

*   **Integration Coverage:** High. All mandatory services identified in the BRD are present and configured.
*   **Critical Gaps:** The primary gap is the `consent_token` for the Aarogya Health API. This is expected behavior for OAuth 2.0 flows, but the implementation team must ensure the `credential_resolve_hook` or a custom session handler correctly injects this token before the API call.
*   **Confidence Level:** **High**. The pipeline is configured to handle the specific security requirements (encryption, masking, and retry logic) defined in the BRD. The use of hooks for audit and failure alerts ensures compliance with the stated security and operational requirements.