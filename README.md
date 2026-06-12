# CSV -> EDI 837P Generator (MassHealth)

This project converts a claim CSV into an X12 5010 837P file suitable for MassHealth TEST submission.

## Files

- `generate_837p.py` - generator and validator
- `csv_schema.md` - required CSV schema and rules
- `mapping_document.md` - CSV -> X12 mapping
- `sample_claims.csv` - sample input
- `sample_837p_test.edi` - sample output generated from sample CSV

## Run

```bash
python generate_837p.py \
  --input sample_claims.csv \
  --output sample_837p_test.edi \
  --submitter-id YOURSUBMITTERID \
  --receiver-id MASSHEALTH \
  --submitter-name "YOUR ORG" \
  --contact-name "EDI CONTACT" \
  --contact-phone 8005551234 \
  --contact-email edi@example.com \
  --environment TEST
```

## If your input format is:

`Medicaid Number,Last Name,First Name,Birth Date,Gender`

The generator now supports it, but you must provide default claim/service/provider values:

```bash
python generate_837p.py \
  --input Dataset.csv \
  --output dataset_837_test.edi \
  --submitter-id YOURSUBMITTERID \
  --environment TEST \
  --default-member-address "100 Default St" \
  --default-member-city Boston \
  --default-member-state MA \
  --default-member-zip 021110123 \
  --default-service-date 20260408 \
  --default-billing-npi 1234567895 \
  --default-rendering-npi 1942285073 \
  --default-billing-name "YOUR ORG" \
  --default-billing-address "10 Health Way" \
  --default-billing-city Boston \
  --default-billing-state MA \
  --default-billing-zip 021150456 \
  --default-cpt-code 99213 \
  --default-charge-amount 100.00 \
  --default-units 1 \
  --default-place-of-service 11 \
  --default-icd10-1 E119 \
  --default-icd10-2 I10 \
  --skip-invalid-simple-rows \
  --max-claims 15
```

- In simplified mode, one CSV row becomes one claim with one service line.
- Use `--skip-invalid-simple-rows` if source data has missing values.
- Keep `--max-claims 15` for MassHealth testing batches.

## Validation implemented

- Required column/header validation
- Required field checks
- Claim grouping by `claim_id`
- Claim-level consistency across service lines
- NPI format + check digit validation
- ICD-10 format validation
- CPT/HCPCS format validation
- Date normalization to `CCYYMMDD`
- ZIP validation to 9 digits
- Claim total = sum of service line charges
- Segment order and `SE` segment count
- Claim volume cap at 15 per file

## TEST -> PROD switch

- Use `--environment TEST` for testing (ISA15 = `T`)
- Use `--environment PROD` for production (ISA15 = `P`)

No code changes are required; only the CLI flag changes.

## MassHealth test submission reminders

1. Submit one test file at a time per transaction type.
2. Upload in the POSC test endpoint.
3. Use production POSC credentials on test site.
4. After submission, email MassHealth with:
   - Username
   - Submission date
   - Submitter ID
   - Tracking number
