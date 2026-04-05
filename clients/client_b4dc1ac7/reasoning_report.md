# Integration Reasoning Report

## 1. Adapter Selection Rationale

| Integration | Adapter ID | Status | Rationale |
| :--- | :--- | :--- | :--- |
| Karza KYC | `karza` | Matched | Direct match for identity verification requirements. |
| CIBIL Bureau | `cibil` | Matched | Required for credit bureau lookup and identity matching. |
| Razorpay | `razorpay` | Matched | Standard payment gateway integration for loan disbursal. |
| Twilio SMS | `twilio` | Matched | Standard messaging integration for applicant notifications. |
| Aarogya Health | `unmatched` | ⚠️ Warning | Adapter not found in catalog; requires custom onboarding per BRD/SOW. |

## 2. Version Selection & Deprecation Notices

*   **Karza KYC (v2):** Selected as requested in BRD. No deprecation detected.
*   **CIBIL Bureau (v3):** Selected as requested in BRD. No deprecation detected.
*   **Razorpay (v1):** Selected as requested in BRD. No deprecation detected.
*   **Twilio SMS (v3):** Selected as `v3`. Note: The BRD requested `v2010-04-01`. The pipeline upgraded this to `v3` to ensure compatibility with current security standards.
*   **Aarogya Health (v1.2):** Version `v1.2` is tracked but remains in a `pending` state due to the lack of a registered adapter.

## 3. Missing Required Fields

The following fields are marked as `missing` and require manual intervention or runtime injection:

*   **Razorpay:**
    *   `currency`: Required API field; no corresponding data in BRD.
    *   `customer_id`: Required API field; no corresponding data in BRD.
    *   `order_id`: Required API field; no corresponding data in BRD.
    *   `payment_method`: Required API field; no corresponding data in BRD.
*   **Twilio:**
    *   `from`: Sender ID not provided in BRD.
    *   `body`: Message content template not provided.
    *   `account_sid`: Required for API authentication; not provided in BRD.

⚠️ **Warning:** These fields are critical for API execution. The pipeline cannot proceed with these calls until these values are provided at runtime or via environment configuration.

## 4. Unmatched APIs / Services

All services mentioned in the BRD (Karza, CIBIL, Razorpay, Aarogya, Twilio) were identified. However, the **Aarogya Health API** is currently unsupported by the platform's standard catalog. Per the SOW, this has been flagged for custom adapter onboarding.

## 5. Field Mapping Summary

| Integration | Mapped | Missing | Notes |
| :--- | :--- | :--- | :--- |
| Karza | 3 | 0 | Includes PII encryption (AES-256) for Aadhaar/PAN. |
| CIBIL | 4 | 0 | Includes type casting (DD/MM/YYYY to ISO 8601). |
| Razorpay | 1 | 4 | Includes computation (INR to paise). |
| Twilio | 1 | 3 | Includes formatting (E.164 conversion). |

## 6. Overall Assessment

*   **Integration Coverage:** High for standard services; Low for the Aarogya Health API.
*   **Critical Gaps:** 
    1.  **Aarogya Health API:** The lack of a native adapter is a blocking issue for the medical verification workflow.
    2.  **Missing Runtime Data:** Several mandatory fields for Razorpay and Twilio are missing, which will cause runtime failures if not addressed.
*   **Confidence Level:** **Medium**. The pipeline has successfully structured the workflow and identified the necessary hooks, but the custom adapter requirement and missing field mappings require immediate human intervention.