# CSV Schema for 837P Generator (MassHealth)

## Required columns

| Column | Type | Required | Rule |
|---|---|---:|---|
| claim_id | string | Yes | Same `claim_id` across rows means same claim |
| subscriber_id | string | Yes | Member identifier used in `NM1*IL` |
| member_first_name | string | Yes | Subscriber first name |
| member_last_name | string | Yes | Subscriber last name |
| member_dob | date | Yes | `CCYYMMDD` or `YYYY-MM-DD` input; output `CCYYMMDD` |
| member_gender | string | Yes | `M`, `F`, or `U` |
| member_address | string | Yes | Subscriber address line |
| member_city | string | Yes | Subscriber city |
| member_state | string | Yes | 2-char state |
| member_zip | string | Yes | 9 digits (ZIP+4, no dash required) |
| service_date | date | Yes | `CCYYMMDD` or `YYYY-MM-DD`; output `CCYYMMDD` |
| billing_npi | string | Yes | 10 digits, valid NPI check digit |
| rendering_npi | string | Yes | 10 digits, valid NPI check digit |
| billing_name | string | Yes | Billing provider/org name |
| billing_address | string | Yes | Billing address |
| billing_city | string | Yes | Billing city |
| billing_state | string | Yes | 2-char state |
| billing_zip | string | Yes | 9 digits (ZIP+4) |
| cpt_code | string | Yes | 5-digit CPT or alphanumeric HCPCS format |
| charge_amount | decimal | Yes | Positive currency amount |
| units | integer | Yes | Positive integer |
| place_of_service | string | Yes | 2-digit POS code |
| icd10_1 | string | Yes | ICD-10 primary diagnosis |
| icd10_2 | string | Yes | ICD-10 secondary diagnosis |

## Row-level behavior

- One CSV row = one 837P service line (`2400` loop).
- Multiple rows with the same `claim_id` are grouped into one claim (`2300` loop).
- Claim-level fields must remain consistent across rows sharing the same `claim_id`.
- Maximum claims per file: 15 (MassHealth test rule guardrail).

## Alternate simplified input format (supported)

If your source file only has the columns below, it is accepted in simplified mode:

- `Medicaid Number`
- `Last Name`
- `First Name`
- `Birth Date`
- `Gender`

For this mode, the generator requires all `--default-*` CLI arguments to supply missing claim/service/provider fields.

- One source row becomes one claim and one service line.
- Invalid rows can be skipped with `--skip-invalid-simple-rows`.