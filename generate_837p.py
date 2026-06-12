#!/usr/bin/env python3
"""CSV -> X12 5010 837P generator for MassHealth testing.

This script converts claim/service-line CSV data into a single 837P transaction
(005010X222A1) with basic validation and MassHealth-oriented envelope settings.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional


REQUIRED_COLUMNS = {
    "claim_id",
    "subscriber_id",
    "member_first_name",
    "member_last_name",
    "member_dob",
    "member_gender",
    "member_address",
    "member_city",
    "member_state",
    "member_zip",
    "service_date",
    "billing_npi",
    "rendering_npi",
    "billing_name",
    "billing_address",
    "billing_city",
    "billing_state",
    "billing_zip",
    "cpt_code",
    "charge_amount",
    "units",
    "place_of_service",
    "icd10_1",
    "icd10_2",
}

SIMPLE_COLUMNS = {
    "Medicaid Number",
    "Last Name",
    "First Name",
    "Birth Date",
    "Gender",
}

ICD10_RE = re.compile(r"^[A-TV-Z][0-9][0-9AB](?:[0-9A-TV-Z]{0,4})$")
CPT_RE = re.compile(r"^(?:[0-9]{5}|[A-Z][0-9A-Z]{4})$")
ZIP9_RE = re.compile(r"^[0-9]{9}$")


@dataclass
class ServiceLine:
    claim_id: str
    service_date: str
    cpt_code: str
    charge_amount: Decimal
    units: int
    place_of_service: str


@dataclass
class Claim:
    claim_id: str
    subscriber_id: str
    member_first_name: str
    member_last_name: str
    member_dob: str
    member_gender: str
    member_address: str
    member_city: str
    member_state: str
    member_zip: str
    billing_npi: str
    rendering_npi: str
    billing_name: str
    billing_address: str
    billing_city: str
    billing_state: str
    billing_zip: str
    icd10_1: str
    icd10_2: str
    lines: List[ServiceLine]

    @property
    def total_charge(self) -> Decimal:
        return sum((line.charge_amount for line in self.lines), Decimal("0.00"))


class ValidationError(Exception):
    pass


def clean(value: str) -> str:
    return (value or "").strip()


def normalize_date(value: str, field_name: str) -> str:
    value = clean(value)
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise ValidationError(f"{field_name} must be CCYYMMDD or YYYY-MM-DD: {value}")


def validate_gender(value: str) -> str:
    value = clean(value).upper()
    if value not in {"M", "F", "U"}:
        raise ValidationError(f"member_gender must be M/F/U: {value}")
    return value


def validate_npi(npi: str, field_name: str) -> str:
    npi = clean(npi)
    if not re.fullmatch(r"\d{10}", npi):
        raise ValidationError(f"{field_name} must be exactly 10 digits")

    # NPI check digit using Luhn on prefix '80840' + first 9 digits.
    base = "80840" + npi[:9]
    digits = [int(d) for d in base]
    total = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    check_digit = (10 - (total % 10)) % 10
    if check_digit != int(npi[-1]):
        raise ValidationError(f"{field_name} has invalid NPI check digit: {npi}")
    return npi


def validate_zip9(value: str, field_name: str) -> str:
    value = re.sub(r"[^0-9]", "", clean(value))
    if not ZIP9_RE.fullmatch(value):
        raise ValidationError(f"{field_name} must be 9 digits (ZIP+4): {value}")
    return value


def validate_icd10(value: str, field_name: str) -> str:
    value = clean(value).upper().replace(".", "")
    if not ICD10_RE.fullmatch(value):
        raise ValidationError(f"{field_name} is not a valid ICD-10 format: {value}")
    return value


def validate_cpt(value: str) -> str:
    value = clean(value).upper()
    if not CPT_RE.fullmatch(value):
        raise ValidationError(f"cpt_code must be valid CPT/HCPCS format: {value}")
    return value


def validate_money(value: str, field_name: str) -> Decimal:
    try:
        amount = Decimal(clean(value)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValidationError(f"{field_name} must be numeric: {value}") from exc
    if amount <= 0:
        raise ValidationError(f"{field_name} must be greater than 0")
    return amount


def validate_units(value: str) -> int:
    if not clean(value).isdigit():
        raise ValidationError(f"units must be a positive integer: {value}")
    units = int(value)
    if units <= 0:
        raise ValidationError("units must be greater than 0")
    return units


def build_defaults_from_args(args: argparse.Namespace) -> Optional[Dict[str, str]]:
    simple_default_fields = [
        "default_member_address",
        "default_member_city",
        "default_member_state",
        "default_member_zip",
        "default_service_date",
        "default_billing_npi",
        "default_rendering_npi",
        "default_billing_name",
        "default_billing_address",
        "default_billing_city",
        "default_billing_state",
        "default_billing_zip",
        "default_cpt_code",
        "default_charge_amount",
        "default_units",
        "default_place_of_service",
        "default_icd10_1",
        "default_icd10_2",
    ]
    provided = {name: getattr(args, name) for name in simple_default_fields}
    if not any(provided.values()):
        return None
    missing = [name for name, value in provided.items() if not value]
    if missing:
        raise ValidationError(
            "Simple input format detected/provided, but required default fields are missing: "
            f"{missing}"
        )

    return {
        "member_address": clean(args.default_member_address),
        "member_city": clean(args.default_member_city),
        "member_state": clean(args.default_member_state).upper(),
        "member_zip": validate_zip9(args.default_member_zip, "default_member_zip"),
        "service_date": normalize_date(args.default_service_date, "default_service_date"),
        "billing_npi": validate_npi(args.default_billing_npi, "default_billing_npi"),
        "rendering_npi": validate_npi(args.default_rendering_npi, "default_rendering_npi"),
        "billing_name": clean(args.default_billing_name),
        "billing_address": clean(args.default_billing_address),
        "billing_city": clean(args.default_billing_city),
        "billing_state": clean(args.default_billing_state).upper(),
        "billing_zip": validate_zip9(args.default_billing_zip, "default_billing_zip"),
        "cpt_code": validate_cpt(args.default_cpt_code),
        "charge_amount": str(validate_money(args.default_charge_amount, "default_charge_amount")),
        "units": str(validate_units(args.default_units)),
        "place_of_service": clean(args.default_place_of_service),
        "icd10_1": validate_icd10(args.default_icd10_1, "default_icd10_1"),
        "icd10_2": validate_icd10(args.default_icd10_2, "default_icd10_2"),
    }


def _is_simple_format(fieldnames: List[str]) -> bool:
    return SIMPLE_COLUMNS.issubset(set(fieldnames))


def parse_claims(
    csv_path: Path,
    max_claims: int = 15,
    simple_defaults: Optional[Dict[str, str]] = None,
    skip_invalid_simple_rows: bool = False,
) -> Dict[str, Claim]:
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValidationError("CSV is missing header row")

        if _is_simple_format(reader.fieldnames):
            if simple_defaults is None:
                raise ValidationError(
                    "Detected simplified CSV format (Medicaid Number, Last Name, First Name, Birth Date, Gender). "
                    "To generate 837P from this format, pass all --default-* arguments for missing claim/service/provider fields."
                )
            return _parse_simple_claims(
                reader,
                max_claims=max_claims,
                defaults=simple_defaults,
                skip_invalid_rows=skip_invalid_simple_rows,
            )

        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValidationError(f"CSV is missing required columns: {sorted(missing)}")

        claims: Dict[str, Claim] = OrderedDict()
        row_num = 1
        for row in reader:
            row_num += 1
            try:
                claim_id = clean(row["claim_id"])
                if not claim_id:
                    raise ValidationError("claim_id is required")

                line = ServiceLine(
                    claim_id=claim_id,
                    service_date=normalize_date(row["service_date"], "service_date"),
                    cpt_code=validate_cpt(row["cpt_code"]),
                    charge_amount=validate_money(row["charge_amount"], "charge_amount"),
                    units=validate_units(row["units"]),
                    place_of_service=clean(row["place_of_service"]),
                )
                if not line.place_of_service or not re.fullmatch(r"\d{2}", line.place_of_service):
                    raise ValidationError("place_of_service must be 2 digits")

                if claim_id not in claims:
                    claims[claim_id] = Claim(
                        claim_id=claim_id,
                        subscriber_id=clean(row["subscriber_id"]),
                        member_first_name=clean(row["member_first_name"]),
                        member_last_name=clean(row["member_last_name"]),
                        member_dob=normalize_date(row["member_dob"], "member_dob"),
                        member_gender=validate_gender(row["member_gender"]),
                        member_address=clean(row["member_address"]),
                        member_city=clean(row["member_city"]),
                        member_state=clean(row["member_state"]).upper(),
                        member_zip=validate_zip9(row["member_zip"], "member_zip"),
                        billing_npi=validate_npi(row["billing_npi"], "billing_npi"),
                        rendering_npi=validate_npi(row["rendering_npi"], "rendering_npi"),
                        billing_name=clean(row["billing_name"]),
                        billing_address=clean(row["billing_address"]),
                        billing_city=clean(row["billing_city"]),
                        billing_state=clean(row["billing_state"]).upper(),
                        billing_zip=validate_zip9(row["billing_zip"], "billing_zip"),
                        icd10_1=validate_icd10(row["icd10_1"], "icd10_1"),
                        icd10_2=validate_icd10(row["icd10_2"], "icd10_2"),
                        lines=[],
                    )
                    _validate_required_claim_fields(claims[claim_id])
                else:
                    _validate_consistent_claim_header(claims[claim_id], row)

                claims[claim_id].lines.append(line)
            except ValidationError as exc:
                raise ValidationError(f"Row {row_num}: {exc}") from exc

    if not claims:
        raise ValidationError("CSV has no claim data rows")
    if len(claims) > max_claims:
        raise ValidationError(f"File has {len(claims)} claims. MassHealth test limit is {max_claims}.")
    return claims


def _parse_simple_claims(
    reader: csv.DictReader,
    max_claims: int,
    defaults: Dict[str, str],
    skip_invalid_rows: bool,
) -> Dict[str, Claim]:
    claims: Dict[str, Claim] = OrderedDict()
    row_num = 1
    claim_seq = 1
    skipped_rows: List[str] = []
    for row in reader:
        row_num += 1
        try:
            subscriber_id = clean(row.get("Medicaid Number", ""))
            if not subscriber_id:
                raise ValidationError("Medicaid Number is required")

            claim_id = f"CLM{claim_seq:06d}"
            claim_seq += 1

            line = ServiceLine(
                claim_id=claim_id,
                service_date=normalize_date(defaults["service_date"], "default_service_date"),
                cpt_code=validate_cpt(defaults["cpt_code"]),
                charge_amount=validate_money(defaults["charge_amount"], "default_charge_amount"),
                units=validate_units(defaults["units"]),
                place_of_service=clean(defaults["place_of_service"]),
            )
            if not line.place_of_service or not re.fullmatch(r"\d{2}", line.place_of_service):
                raise ValidationError("default_place_of_service must be 2 digits")

            claim = Claim(
                claim_id=claim_id,
                subscriber_id=subscriber_id,
                member_first_name=clean(row.get("First Name", "")),
                member_last_name=clean(row.get("Last Name", "")),
                member_dob=normalize_date(row.get("Birth Date", ""), "Birth Date"),
                member_gender=validate_gender(row.get("Gender", "")),
                member_address=defaults["member_address"],
                member_city=defaults["member_city"],
                member_state=defaults["member_state"],
                member_zip=validate_zip9(defaults["member_zip"], "default_member_zip"),
                billing_npi=validate_npi(defaults["billing_npi"], "default_billing_npi"),
                rendering_npi=validate_npi(defaults["rendering_npi"], "default_rendering_npi"),
                billing_name=defaults["billing_name"],
                billing_address=defaults["billing_address"],
                billing_city=defaults["billing_city"],
                billing_state=defaults["billing_state"],
                billing_zip=validate_zip9(defaults["billing_zip"], "default_billing_zip"),
                icd10_1=validate_icd10(defaults["icd10_1"], "default_icd10_1"),
                icd10_2=validate_icd10(defaults["icd10_2"], "default_icd10_2"),
                lines=[line],
            )
            _validate_required_claim_fields(claim)
            claims[claim_id] = claim
        except ValidationError as exc:
            if skip_invalid_rows:
                skipped_rows.append(f"Row {row_num}: {exc}")
                continue
            raise ValidationError(f"Row {row_num}: {exc}") from exc

    if not claims:
        raise ValidationError("CSV has no claim data rows")
    if skipped_rows:
        print(f"Skipped {len(skipped_rows)} invalid simplified row(s).")
        for item in skipped_rows[:10]:
            print(f"  - {item}")
        if len(skipped_rows) > 10:
            print(f"  - ... {len(skipped_rows) - 10} more skipped row(s)")
    if len(claims) > max_claims:
        raise ValidationError(f"File has {len(claims)} claims. MassHealth test limit is {max_claims}.")
    return claims


def _validate_required_claim_fields(claim: Claim) -> None:
    required = {
        "subscriber_id": claim.subscriber_id,
        "member_first_name": claim.member_first_name,
        "member_last_name": claim.member_last_name,
        "member_address": claim.member_address,
        "member_city": claim.member_city,
        "member_state": claim.member_state,
        "billing_name": claim.billing_name,
        "billing_address": claim.billing_address,
        "billing_city": claim.billing_city,
        "billing_state": claim.billing_state,
    }
    missing = [k for k, v in required.items() if not clean(v)]
    if missing:
        raise ValidationError(f"Missing required claim-level fields: {missing}")


def _validate_consistent_claim_header(claim: Claim, row: Dict[str, str]) -> None:
    checks = {
        "subscriber_id": claim.subscriber_id == clean(row["subscriber_id"]),
        "member_first_name": claim.member_first_name == clean(row["member_first_name"]),
        "member_last_name": claim.member_last_name == clean(row["member_last_name"]),
        "billing_npi": claim.billing_npi == clean(row["billing_npi"]),
        "rendering_npi": claim.rendering_npi == clean(row["rendering_npi"]),
        "icd10_1": claim.icd10_1 == validate_icd10(row["icd10_1"], "icd10_1"),
        "icd10_2": claim.icd10_2 == validate_icd10(row["icd10_2"], "icd10_2"),
    }
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        raise ValidationError(f"Inconsistent claim-level data across service lines for {bad}")


def fmt_money(amount: Decimal) -> str:
    return f"{amount:.2f}"


def x12_escape(value: str) -> str:
    # Remove separators and segment terminator from free text fields.
    return (
        clean(value)
        .replace("*", " ")
        .replace(":", " ")
        .replace("~", " ")
        .replace("^", " ")
    )


def build_edi(
    claims: Dict[str, Claim],
    submitter_id: str,
    receiver_id: str,
    submitter_name: str,
    submitter_contact_name: str,
    submitter_phone: str,
    submitter_email: str,
    environment: str,
) -> str:
    now = datetime.now()
    isa_date = now.strftime("%y%m%d")
    isa_time = now.strftime("%H%M")
    long_date = now.strftime("%Y%m%d")
    long_time = now.strftime("%H%M")

    control_num_isa = "000000905"
    control_num_gs = "1"
    control_num_st = "0001"

    submitter_id_15 = submitter_id[:15].ljust(15)
    receiver_id_15 = receiver_id[:15].ljust(15)

    segments: List[str] = []

    segments.append(
        "*".join(
            [
                "ISA",
                "00",
                "".ljust(10),
                "00",
                "".ljust(10),
                "ZZ",
                submitter_id_15,
                "ZZ",
                receiver_id_15,
                isa_date,
                isa_time,
                "^",
                "00501",
                control_num_isa,
                "0",
                "T" if environment == "TEST" else "P",
                ":",
            ]
        )
    )

    segments.append(
        f"GS*HC*{x12_escape(submitter_id)}*{x12_escape(receiver_id)}*{long_date}*{long_time}*{control_num_gs}*X*005010X222A1"
    )

    st_index = len(segments)
    segments.append(f"ST*837*{control_num_st}*005010X222A1")
    segments.append(f"BHT*0019*00*{long_date}{long_time}*{long_date}*{long_time}*CH")

    # 1000A Submitter
    segments.append(f"NM1*41*2*{x12_escape(submitter_name)}*****46*{x12_escape(submitter_id)}")
    segments.append(
        f"PER*IC*{x12_escape(submitter_contact_name)}*TE*{x12_escape(submitter_phone)}*EM*{x12_escape(submitter_email)}"
    )

    # 1000B Receiver
    segments.append(f"NM1*40*2*MASSHEALTH*****46*{x12_escape(receiver_id)}")

    # Group claims by billing provider NPI for proper 2000A hierarchy.
    provider_groups: Dict[str, List[Claim]] = OrderedDict()
    for claim in claims.values():
        provider_groups.setdefault(claim.billing_npi, []).append(claim)

    hl_id = 0
    for provider_npi, provider_claims in provider_groups.items():
        sample_claim = provider_claims[0]

        # 2000A Billing Provider HL
        hl_id += 1
        billing_hl_id = hl_id
        segments.append(f"HL*{billing_hl_id}**20*1")
        segments.append("PRV*BI*PXC*207Q00000X")

        # 2010AA Billing Provider Name
        segments.append(f"NM1*85*2*{x12_escape(sample_claim.billing_name)}*****XX*{provider_npi}")
        segments.append(f"N3*{x12_escape(sample_claim.billing_address)}")
        segments.append(
            f"N4*{x12_escape(sample_claim.billing_city)}*{sample_claim.billing_state}*{sample_claim.billing_zip}"
        )
        segments.append("REF*EI*123456789")

        for claim in provider_claims:
            # 2000B Subscriber HL
            hl_id += 1
            subscriber_hl_id = hl_id
            segments.append(f"HL*{subscriber_hl_id}*{billing_hl_id}*22*0")
            segments.append("SBR*P*18*******MC")

            # 2010BA Subscriber
            segments.append(
                f"NM1*IL*1*{x12_escape(claim.member_last_name)}*{x12_escape(claim.member_first_name)}****MI*{x12_escape(claim.subscriber_id)}"
            )
            segments.append(f"N3*{x12_escape(claim.member_address)}")
            segments.append(f"N4*{x12_escape(claim.member_city)}*{claim.member_state}*{claim.member_zip}")
            segments.append(f"DMG*D8*{claim.member_dob}*{claim.member_gender}")

            # 2010BB Payer
            segments.append("NM1*PR*2*MASSHEALTH*****PI*MASSHEALTH")

            # 2300 Claim Information
            segments.append(f"CLM*{x12_escape(claim.claim_id)}*{fmt_money(claim.total_charge)}***11:B:1*Y*A*Y*I")
            min_service = min(line.service_date for line in claim.lines)
            max_service = max(line.service_date for line in claim.lines)
            if min_service == max_service:
                segments.append(f"DTP*431*D8*{min_service}")
            else:
                segments.append(f"DTP*431*RD8*{min_service}-{max_service}")

            segments.append(f"HI*ABK:{claim.icd10_1}*ABF:{claim.icd10_2}")

            # 2310B Rendering Provider
            segments.append(f"NM1*82*2*RENDERING PROVIDER*****XX*{claim.rendering_npi}")

            # 2400 Service Lines
            for idx, line in enumerate(claim.lines, start=1):
                segments.append(f"LX*{idx}")
                segments.append(
                    f"SV1*HC:{line.cpt_code}*{fmt_money(line.charge_amount)}*UN*{line.units}***{line.place_of_service}*1"
                )
                segments.append(f"DTP*472*D8*{line.service_date}")

    se_count = (len(segments) - st_index) + 1  # include SE itself
    segments.append(f"SE*{se_count}*{control_num_st}")
    segments.append(f"GE*1*{control_num_gs}")
    segments.append(f"IEA*1*{control_num_isa}")

    return "~\n".join(segments) + "~\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate MassHealth test 837P EDI from CSV.")
    parser.add_argument("--input", required=True, help="Path to input CSV")
    parser.add_argument("--output", required=True, help="Path to output .edi/.txt file")
    parser.add_argument("--submitter-id", required=True, help="MassHealth submitter ID")
    parser.add_argument("--receiver-id", default="MASSHEALTH", help="MassHealth receiver ID")
    parser.add_argument("--submitter-name", default="YOUR ORG NAME", help="Submitter organization name")
    parser.add_argument("--contact-name", default="EDI CONTACT", help="Submitter contact person")
    parser.add_argument("--contact-phone", default="8005551234", help="Submitter contact phone")
    parser.add_argument("--contact-email", default="edi@example.com", help="Submitter contact email")
    parser.add_argument(
        "--environment",
        choices=["TEST", "PROD"],
        default="TEST",
        help="ISA15 value selector (TEST=T, PROD=P)",
    )
    parser.add_argument("--default-member-address", help="Required for simplified input format")
    parser.add_argument("--default-member-city", help="Required for simplified input format")
    parser.add_argument("--default-member-state", help="Required for simplified input format")
    parser.add_argument("--default-member-zip", help="Required for simplified input format")
    parser.add_argument("--default-service-date", help="Required for simplified input format")
    parser.add_argument("--default-billing-npi", help="Required for simplified input format")
    parser.add_argument("--default-rendering-npi", help="Required for simplified input format")
    parser.add_argument("--default-billing-name", help="Required for simplified input format")
    parser.add_argument("--default-billing-address", help="Required for simplified input format")
    parser.add_argument("--default-billing-city", help="Required for simplified input format")
    parser.add_argument("--default-billing-state", help="Required for simplified input format")
    parser.add_argument("--default-billing-zip", help="Required for simplified input format")
    parser.add_argument("--default-cpt-code", help="Required for simplified input format")
    parser.add_argument("--default-charge-amount", help="Required for simplified input format")
    parser.add_argument("--default-units", help="Required for simplified input format")
    parser.add_argument("--default-place-of-service", help="Required for simplified input format")
    parser.add_argument("--default-icd10-1", help="Required for simplified input format")
    parser.add_argument("--default-icd10-2", help="Required for simplified input format")
    parser.add_argument(
        "--skip-invalid-simple-rows",
        action="store_true",
        help="Skip rows with missing/invalid values when using simplified input format",
    )
    parser.add_argument(
        "--max-claims",
        type=int,
        default=15,
        help="Maximum claims allowed in a generated file (default: 15)",
    )

    args = parser.parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    simple_defaults = build_defaults_from_args(args)
    claims = parse_claims(
        input_path,
        max_claims=args.max_claims,
        simple_defaults=simple_defaults,
        skip_invalid_simple_rows=args.skip_invalid_simple_rows,
    )
    edi = build_edi(
        claims=claims,
        submitter_id=args.submitter_id,
        receiver_id=args.receiver_id,
        submitter_name=args.submitter_name,
        submitter_contact_name=args.contact_name,
        submitter_phone=args.contact_phone,
        submitter_email=args.contact_email,
        environment=args.environment,
    )

    output_path.write_text(edi, encoding="utf-8", newline="")
    print(f"Generated {output_path} with {len(claims)} claim(s).")


if __name__ == "__main__":
    main()
