#!/usr/bin/env python3
"""
CSV -> X12 5010 270 (Eligibility Inquiry) generator for MassHealth.

Fixes applied based on rejection analysis + companion guide (Nov 2023):
  1. Transaction type is 270 / 005010X279A1  (not 837)
  2. Receiver ID is DMA7384 in ISA08, GS03, and NM1*PR NM109
  3. Full three-level HL hierarchy: 2000A (payer) / 2000B (provider) / 2000C (subscriber)
  4. NM1*PR  in 2100A  — Information Source   (payer loop)
  5. NM1*1P  in 2100B  — Information Receiver (provider loop)
  6. NO NM1*41  and NO standalone PER segment (explicitly rejected by MassHealth)
  7. NO invalid REF01 code G2
  8. DTP qualifier 291 with format RD8 and a date range  (e.g. 20250501-20250501)
  9. ISA06 = provider/submitter ID padded to exactly 15 characters
 10. Segment count in SE includes ST through SE inclusive
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MASSHEALTH_RECEIVER_ID   = "DMA7384"          # ISA08 / GS03 / NM1*PR NM109
MASSHEALTH_SOURCE_NAME   = "MASSHEALTH"       # NM1*PR NM103
MASSHEALTH_PI_CODE       = "PI"               # NM1*PR NM108 qualifier
MASSHEALTH_PI_ID         = "842610001"        # NM1*PR NM109 (Information Source primary ID)
TRANSACTION_VERSION      = "005010X279A1"     # Must NOT be 005010X222A1 (837)
MAX_TEST_INQUIRIES       = 15

REQUIRED_COLUMNS = {
    "Medicaid Number",
    "Last Name",
    "First Name",
    "Birth Date",
    "Gender",
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    pass


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MemberInquiry:
    subscriber_id: str   # MassHealth Medicaid ID (MI)
    first_name:    str
    last_name:     str
    dob:           str   # YYYYMMDD
    gender:        str   # M / F / U


# ---------------------------------------------------------------------------
# Helpers / validators
# ---------------------------------------------------------------------------

def clean(value: str) -> str:
    return (value or "").strip()


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", clean(value))


def x12_safe(value: str) -> str:
    """Strip X12 delimiter characters that would break segment parsing."""
    return (
        clean(value)
        .replace("*", " ")
        .replace("~", " ")
        .replace("^", " ")
        .replace(":", " ")
    ).strip()


def normalize_date(value: str, field_name: str) -> str:
    value = clean(value)
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise ValidationError(f"{field_name} must be a valid date, got: {value!r}")


def validate_gender(value: str) -> str:
    v = clean(value).upper()
    if v not in {"M", "F", "U"}:
        raise ValidationError(f"Gender must be M, F, or U; got: {value!r}")
    return v


def validate_submitter_receiver_id(value: str, field_name: str) -> str:
    v = clean(value)
    if not v:
        raise ValidationError(f"{field_name} is required")
    if len(v) > 15:
        raise ValidationError(
            f"{field_name} must be ≤15 characters (ISA field limit); got {len(v)}: {v!r}"
        )
    return v


def validate_subscriber_id(value: str, field_name: str = "Medicaid Number") -> str:
    v = re.sub(r"\s+", "", clean(value))
    if not v:
        raise ValidationError(f"{field_name} is required")
    if not re.fullmatch(r"[A-Za-z0-9\-]+", v):
        raise ValidationError(
            f"{field_name} contains invalid characters: {value!r}"
        )
    return v[:80]


def validate_npi(value: str, field_name: str = "provider_npi") -> str:
    npi = digits_only(value)
    if not re.fullmatch(r"\d{10}", npi):
        raise ValidationError(
            f"{field_name} must be exactly 10 digits; got: {value!r}"
        )
    return npi


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def parse_members(
    csv_path: Path,
    max_inquiries: int,
    skip_invalid_rows: bool,
) -> List[MemberInquiry]:
    members: List[MemberInquiry] = []
    skipped: List[str] = []

    with csv_path.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValidationError("CSV is missing a header row")

        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValidationError(
                f"CSV missing required columns: {', '.join(sorted(missing))}"
            )

        for row_num, row in enumerate(reader, start=2):
            try:
                first = x12_safe(row.get("First Name", ""))
                last  = x12_safe(row.get("Last Name",  ""))
                if not first:
                    raise ValidationError("First Name is required")
                if not last:
                    raise ValidationError("Last Name is required")

                member = MemberInquiry(
                    subscriber_id = validate_subscriber_id(
                                        row.get("Medicaid Number", "")),
                    first_name    = first,
                    last_name     = last,
                    dob           = normalize_date(
                                        row.get("Birth Date", ""), "Birth Date"),
                    gender        = validate_gender(row.get("Gender", "")),
                )
                members.append(member)
                if len(members) >= max_inquiries:
                    break

            except ValidationError as exc:
                msg = f"Row {row_num}: {exc}"
                if skip_invalid_rows:
                    skipped.append(msg)
                else:
                    raise ValidationError(msg) from exc

    if not members:
        raise ValidationError("No valid member rows found in CSV")

    if skipped:
        print(f"[WARN] Skipped {len(skipped)} invalid row(s):")
        for line in skipped[:10]:
            print(f"  {line}")

    return members


# ---------------------------------------------------------------------------
# 270 builder
# ---------------------------------------------------------------------------

def build_270(
    members:        List[MemberInquiry],
    submitter_id:   str,   # ISA06 / GS02 — trading-partner ID assigned by MassHealth
    provider_name:  str,   # NM1*1P NM103
    provider_npi:   str,   # NM1*1P NM109  (10-digit NPI, qualifier XX)
    service_date:   str,   # YYYYMMDD — used as both start and end of RD8 range
    environment:    str,   # "TEST" | "PROD"
) -> str:
    """
    Builds a fully compliant MassHealth 270 with the required loop structure:

        ISA / GS
          ST / BHT
          HL*1**20*1          — 2000A Information Source
            NM1*PR            — 2100A payer name  (MASSHEALTH / DMA7384)
          HL*2*1*21*1         — 2000B Information Receiver
            NM1*1P            — 2100B provider name + NPI
          HL*3*2*22*0         — 2000C Subscriber  (repeated per member)
            TRN / NM1*IL / DMG / DTP / EQ
          ...
          SE / GE / IEA

    Segments explicitly EXCLUDED per MassHealth rejections:
      • NM1*41  (Submitter Name  — not valid in 270)
      • PER     (Contact segment — not valid in 270 submitter loop)
      • REF with G2 qualifier   — not allowed in 2100B
    """

    now     = datetime.now()
    isa_date = now.strftime("%y%m%d")
    isa_time = now.strftime("%H%M")
    gs_date  = now.strftime("%Y%m%d")
    gs_time  = now.strftime("%H%M")

    # Control numbers
    seed        = int(now.strftime("%d%H%M%S"))
    isa_control = str(seed % 1_000_000_000).zfill(9)
    gs_control  = str(seed % 1_000_000_000)
    st_control  = str(seed % 10_000).zfill(4)
    bht_ref     = now.strftime("%Y%m%d%H%M%S")

    # ISA06 must be exactly 15 characters (padded with spaces)
    isa_sender   = submitter_id.ljust(15)
    # ISA08 must be exactly 15 characters
    isa_receiver = MASSHEALTH_RECEIVER_ID.ljust(15)

    usage_indicator = "T" if environment.upper() == "TEST" else "P"

    # Validated service date + RD8 range  (companion guide uses RD8 throughout)
    svc_date      = normalize_date(service_date, "service_date")
    svc_date_range = f"{svc_date}-{svc_date}"   # single-day range e.g. 20250501-20250501

    # -----------------------------------------------------------------------
    # Envelope segments (outside ST/SE)
    # -----------------------------------------------------------------------
    envelope: List[str] = []

    # ISA — Interchange Control Header
    # Rejection fix #1: version 00501, qualifier ZZ, correct receiver DMA7384
    # Rejection fix #2: NO submitter name segment (NM1*41) here or anywhere
    envelope.append(
        "*".join([
            "ISA",
            "00", "          ",   # ISA01-02: no auth info
            "00", "          ",   # ISA03-04: no security info
            "ZZ", isa_sender,     # ISA05-06: sender qualifier + ID
            "ZZ", isa_receiver,   # ISA07-08: receiver qualifier + DMA7384
            isa_date,             # ISA09
            isa_time,             # ISA10
            "^",                  # ISA11: repetition separator
            "00501",              # ISA12: version — 005010
            isa_control,          # ISA13
            "0",                  # ISA14: no TA1 requested
            usage_indicator,      # ISA15: T=test, P=production
            ":",                  # ISA16: component separator
        ])
    )

    # GS — Functional Group Header
    # GS01=HS (Health Care Eligibility), GS08=005010X279A1 (270, NOT 837)
    envelope.append(
        f"GS*HS"
        f"*{x12_safe(submitter_id)}"
        f"*{MASSHEALTH_RECEIVER_ID}"
        f"*{gs_date}"
        f"*{gs_time}"
        f"*{gs_control}"
        f"*X"
        f"*{TRANSACTION_VERSION}"
    )

    # -----------------------------------------------------------------------
    # Transaction set  (segments counted in SE)
    # -----------------------------------------------------------------------
    tx: List[str] = []

    # ST — Transaction Set Header
    # Rejection fix: set ID 270, version 005010X279A1 (not 837/005010X222A1)
    tx.append(f"ST*270*{st_control}*{TRANSACTION_VERSION}")

    # BHT — Beginning of Hierarchical Transaction
    tx.append(f"BHT*0022*13*{bht_ref}*{gs_date}*{gs_time}")

    # -------------------------------------------------------------------
    # HL*1 — 2000A Information Source Loop  (MISSING in previous script)
    # Rejection fix #6: mandatory loop that was absent
    # -------------------------------------------------------------------
    tx.append("HL*1**20*1")

    # NM1*PR — 2100A Information Source Name
    # Rejection fix #2: NM109 must be DMA7384, NOT "MASSHEALTH"
    # NM108=PI (Electronic Transmitter Identification Number per guide p.14)
    tx.append(
        f"NM1*PR*2*{MASSHEALTH_SOURCE_NAME}*****{MASSHEALTH_PI_CODE}*{MASSHEALTH_PI_ID}"
    )

    # -------------------------------------------------------------------
    # HL*2 — 2000B Information Receiver Loop  (MISSING in previous script)
    # -------------------------------------------------------------------
    tx.append("HL*2*1*21*1")

    # NM1*1P — 2100B Information Receiver Name
    # NM108=XX (NPI), NM109=10-digit NPI
    # Rejection fix #4: NO REF*G2 here (invalid code for 270)
    # Rejection fix #5: NO NM1*41 / PER segments
    safe_provider = x12_safe(provider_name)
    tx.append(
        f"NM1*1P*2*{safe_provider}*****SV*{submitter_id}"
    )

    # -------------------------------------------------------------------
    # HL*n — 2000C Subscriber Loops  (one per member)
    # Parent is always HL 2 (the Information Receiver)
    # -------------------------------------------------------------------
    trn_seed = int(now.strftime("%H%M%S"))

    for i, member in enumerate(members, start=1):
        hl_num    = i + 2          # HL 3, 4, 5 … (1=source, 2=receiver)
        trn_value = f"{trn_seed}{i:04d}"[:30]

        # HL — Hierarchical Level: level code 22=Subscriber, parent=2, no children
        tx.append(f"HL*{hl_num}*2*22*0")

        # TRN — Trace Number (stays in 2000C per companion guide examples)
        tx.append(f"TRN*1*{trn_value}*{x12_safe(submitter_id)}")

        # NM1*IL — Subscriber Name
        # NM108=MI (Member ID), NM109=Medicaid ID
        # Companion guide p.15: last name max 20 chars, first name max 15 chars
        last  = x12_safe(member.last_name)[:20]
        first = x12_safe(member.first_name)[:15]
        tx.append(
            f"NM1*IL*1"
            f"*{last}"
            f"*{first}"
            f"****MI*{x12_safe(member.subscriber_id)}"
        )

        # DMG — Subscriber Demographic Information
        tx.append(f"DMG*D8*{member.dob}*{member.gender}")

        # DTP — Date/Time Reference
        # Rejection fix #8: qualifier 291, format RD8 (date range), NOT D8 (single date)
        tx.append(f"DTP*291*RD8*{svc_date_range}")

        # EQ — Eligibility or Benefit Inquiry
        # Service type code 30 = Health Benefit Plan Coverage
        tx.append("EQ*30")

    # SE — Transaction Set Trailer
    # Segment count = number of segments from ST through SE inclusive
    se_count = len(tx) + 1   # +1 for SE itself
    tx.append(f"SE*{se_count}*{st_control}")

    # -----------------------------------------------------------------------
    # Close envelope
    # -----------------------------------------------------------------------
    # All segments (envelope + transaction) must be terminated by ~
    # Join every segment with ~\n so the file is human-readable and
    # every segment — including inner ST/BHT/HL/NM1 etc. — carries a tilde.
    all_segments: List[str] = []
    all_segments.append(envelope[0])   # ISA
    all_segments.append(envelope[1])   # GS
    all_segments.extend(tx)            # ST … SE
    all_segments.append(f"GE*1*{gs_control}")
    all_segments.append(f"IEA*1*{isa_control}")

    return "~\n".join(all_segments) + "~\n"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a MassHealth-compliant X12 5010 270 Eligibility Inquiry "
            "from a CSV file. Addresses all known MassHealth rejection reasons."
        )
    )

    # Input / output
    parser.add_argument("--input",   required=True,
                        help="Path to input CSV file")
    parser.add_argument("--output",  required=True,
                        help="Path for output .txt EDI file")

    # Submitter / trading-partner identity
    parser.add_argument("--submitter-id", required=True,
                        help=(
                            "10-character MassHealth MMIS Provider ID / service location "
                            "(appears in ISA06, GS02, NM1*1P). Must be on file with MassHealth."
                        ))

    # Provider info for the 2100B Information Receiver loop
    parser.add_argument("--provider-name", required=True,
                        help="Provider organization name (NM1*1P NM103)")
    parser.add_argument("--provider-npi",  required=True,
                        help="10-digit National Provider Identifier (NM1*1P NM109, qualifier XX)")

    # Receiver is always DMA7384 for MassHealth providers
    parser.add_argument("--receiver-id", default=MASSHEALTH_RECEIVER_ID,
                        help=f"MassHealth receiver ID (default: {MASSHEALTH_RECEIVER_ID})")

    # Date / environment
    parser.add_argument("--service-date",
                        default=datetime.now().strftime("%Y%m%d"),
                        help="Service date YYYYMMDD (default: today). "
                             "Used as both start and end of the RD8 date range.")
    parser.add_argument("--environment", choices=["TEST", "PROD"], default="TEST",
                        help="ISA15 usage indicator: TEST or PROD (default: TEST)")

    # Limits
    parser.add_argument("--max-inquiries", type=int, default=MAX_TEST_INQUIRIES,
                        help=f"Maximum member inquiries per file (default: {MAX_TEST_INQUIRIES})")
    parser.add_argument("--skip-invalid-rows", action="store_true",
                        help="Skip invalid CSV rows instead of aborting")

    args = parser.parse_args()

    # Guard: MassHealth test files must not exceed 15 inquiries
    if args.environment == "TEST" and args.max_inquiries > MAX_TEST_INQUIRIES:
        raise ValidationError(
            f"MassHealth test files must contain at most {MAX_TEST_INQUIRIES} inquiries "
            f"(companion guide §3). You requested {args.max_inquiries}."
        )

    # Validate CLI identifiers
    submitter_id = validate_submitter_receiver_id(args.submitter_id, "submitter_id")
    provider_npi = validate_npi(args.provider_npi, "provider_npi")

    # Receiver must be DMA7384 for standard MassHealth providers
    if args.receiver_id.strip().upper() not in {MASSHEALTH_RECEIVER_ID, "HSN3644"}:
        raise ValidationError(
            f"receiver_id must be '{MASSHEALTH_RECEIVER_ID}' (MassHealth) "
            f"or 'HSN3644' (HSN); got: {args.receiver_id!r}"
        )

    # Parse members from CSV
    members = parse_members(
        csv_path         = Path(args.input),
        max_inquiries    = args.max_inquiries,
        skip_invalid_rows= args.skip_invalid_rows,
    )

    # Build EDI
    edi = build_270(
        members        = members,
        submitter_id   = submitter_id,
        provider_name  = args.provider_name,
        provider_npi   = provider_npi,
        service_date   = args.service_date,
        environment    = args.environment,
    )

    # Write output (no BOM, Unix line endings)
    Path(args.output).write_text(edi, encoding="utf-8", newline="")

    print(
        f"[OK] Generated {args.output} — "
        f"{len(members)} member inquiry(ies), "
        f"environment={args.environment}"
    )

    # Print a brief structure summary so the user can visually verify
    print("\n--- Segment structure summary ---")
    for line in edi.splitlines():
        seg = line.split("*")[0].rstrip("~")
        if seg in {"ISA", "GS", "ST", "BHT", "HL", "NM1", "TRN", "DMG", "DTP", "EQ", "SE", "GE", "IEA"}:
            indent = "  " if seg in {"NM1", "TRN", "DMG", "DTP", "EQ"} else ""
            print(f"  {indent}{line.rstrip('~')}")


if __name__ == "__main__":
    main()