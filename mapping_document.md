# Mapping: CSV -> X12 5010 837P Segments

## Envelopes

| X12 Segment | Source |
|---|---|
| ISA06 | `--submitter-id` (space padded to 15) |
| ISA08 | `--receiver-id` (space padded to 15) |
| ISA11 | `^` repetition separator |
| ISA15 | `T` in TEST / `P` in PROD (`--environment`) |
| GS02 | `--submitter-id` |
| GS03 | `--receiver-id` |
| ST01 | `837` |
| ST03 | `005010X222A1` |

## 1000A Submitter

| Segment | Mapping |
|---|---|
| NM1*41 | `--submitter-name`, `--submitter-id` |
| PER | `--contact-name`, `--contact-phone`, `--contact-email` |

## 1000B Receiver

| Segment | Mapping |
|---|---|
| NM1*40 | Literal `MASSHEALTH`, receiver ID |

## 2000A / 2010AA Billing Provider

| Segment | Mapping |
|---|---|
| HL (20) | Generated hierarchy level for billing provider |
| PRV*BI | Fixed taxonomy placeholder `207Q00000X` |
| NM1*85 | `billing_name`, `billing_npi` |
| N3 | `billing_address` |
| N4 | `billing_city`, `billing_state`, `billing_zip` |
| REF*EI | Placeholder `123456789` (replace with real Tax ID if required) |

## 2000B / 2010BA Subscriber

| Segment | Mapping |
|---|---|
| HL (22) | Generated hierarchy level under billing HL |
| SBR | `SBR*P*18*******MC` |
| NM1*IL | `member_last_name`, `member_first_name`, `subscriber_id` |
| N3 | `member_address` |
| N4 | `member_city`, `member_state`, `member_zip` |
| DMG | `member_dob`, `member_gender` |

## 2300 Claim

| Segment | Mapping |
|---|---|
| CLM01 | `claim_id` |
| CLM02 | Sum of all `charge_amount` for the claim |
| DTP*431 | Claim statement date range from service lines |
| HI | `icd10_1` as `ABK`, `icd10_2` as `ABF` |

## 2310B Rendering Provider

| Segment | Mapping |
|---|---|
| NM1*82 | Rendering NPI from `rendering_npi` |

## 2400 Service Line

| Segment | Mapping |
|---|---|
| LX | Sequence number per service line |
| SV1-2 | `cpt_code` as `HC:<code>` |
| SV1-3 | `charge_amount` |
| SV1-4 | `UN` |
| SV1-5 | `units` |
| SV1-7 | `place_of_service` |
| DTP*472 | `service_date` |

## Trailer

| Segment | Mapping |
|---|---|
| SE01 | Auto segment count from `ST` through `SE` |
| GE01 | `1` transaction set |
| IEA01 | `1` functional group |
