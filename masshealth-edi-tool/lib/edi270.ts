export const MASSHEALTH_RECEIVER_ID = "DMA7384";
export const HSN_RECEIVER_ID = "HSN3644";
export const MASSHEALTH_SOURCE_NAME = "MASSHEALTH";
export const MASSHEALTH_PI_CODE = "PI";
export const MASSHEALTH_PI_ID = "842610001";
export const TRANSACTION_VERSION = "005010X279A1";
export const MAX_TEST_INQUIRIES = 15;

export const REQUIRED_COLUMNS = [
  "Medicaid Number",
  "Last Name",
  "First Name",
  "Birth Date",
  "Gender",
] as const;

export type Environment = "TEST" | "PROD";

export type MemberInquiry = {
  subscriberId: string;
  firstName: string;
  lastName: string;
  dob: string;
  gender: "M" | "F" | "U";
};

export type CsvPreviewRow = {
  rowNumber: number;
  raw: Record<string, unknown>;
  member?: MemberInquiry;
  errors: string[];
};

export type Build270Options = {
  submitterId: string;
  providerName: string;
  providerNpi: string;
  receiverId: string;
  serviceDate: string;
  environment: Environment;
  maxInquiries: number;
};

export class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
  }
}

export function clean(value: unknown): string {
  return String(value ?? "").trim();
}

export function digitsOnly(value: unknown): string {
  return clean(value).replace(/\D/g, "");
}

export function x12Safe(value: unknown): string {
  return clean(value).replaceAll("*", " ").replaceAll("~", " ").replaceAll("^", " ").replaceAll(":", " ").trim();
}

function parseDateParts(value: string, fieldName: string): [number, number, number] {
  const trimmed = clean(value);
  let match = /^(\d{4})(\d{2})(\d{2})$/.exec(trimmed);
  if (match) return [Number(match[1]), Number(match[2]), Number(match[3])];

  match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(trimmed);
  if (match) return [Number(match[1]), Number(match[2]), Number(match[3])];

  match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(trimmed);
  if (match) return [Number(match[3]), Number(match[1]), Number(match[2])];

  match = /^(\d{1,2})-(\d{1,2})-(\d{4})$/.exec(trimmed);
  if (match) return [Number(match[3]), Number(match[1]), Number(match[2])];

  throw new ValidationError(`${fieldName} must be a valid date, got: ${JSON.stringify(trimmed)}`);
}

export function normalizeDate(value: unknown, fieldName: string): string {
  const [year, month, day] = parseDateParts(clean(value), fieldName);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    throw new ValidationError(`${fieldName} must be a valid date, got: ${JSON.stringify(clean(value))}`);
  }
  return `${year.toString().padStart(4, "0")}${month.toString().padStart(2, "0")}${day
    .toString()
    .padStart(2, "0")}`;
}

export function validateGender(value: unknown): "M" | "F" | "U" {
  const gender = clean(value).toUpperCase();
  if (gender !== "M" && gender !== "F" && gender !== "U") {
    throw new ValidationError(`Gender must be M, F, or U; got: ${JSON.stringify(clean(value))}`);
  }
  return gender;
}

export function validateSubmitterReceiverId(value: unknown, fieldName: string): string {
  const id = clean(value);
  if (!id) throw new ValidationError(`${fieldName} is required`);
  if (id.length > 15) {
    throw new ValidationError(`${fieldName} must be <=15 characters (ISA field limit); got ${id.length}: ${JSON.stringify(id)}`);
  }
  return id;
}

export function validateSubscriberId(value: unknown, fieldName = "Medicaid Number"): string {
  const id = clean(value).replace(/\s+/g, "");
  if (!id) throw new ValidationError(`${fieldName} is required`);
  if (!/^[A-Za-z0-9-]+$/.test(id)) {
    throw new ValidationError(`${fieldName} contains invalid characters: ${JSON.stringify(clean(value))}`);
  }
  return id.slice(0, 80);
}

export function validateNpi(value: unknown, fieldName = "provider_npi"): string {
  const npi = digitsOnly(value);
  if (!/^\d{10}$/.test(npi)) {
    throw new ValidationError(`${fieldName} must be exactly 10 digits; got: ${JSON.stringify(clean(value))}`);
  }
  return npi;
}

export function validateReceiverId(value: unknown): string {
  const receiverId = clean(value).toUpperCase();
  if (receiverId !== MASSHEALTH_RECEIVER_ID && receiverId !== HSN_RECEIVER_ID) {
    throw new ValidationError(`receiver_id must be '${MASSHEALTH_RECEIVER_ID}' (MassHealth) or '${HSN_RECEIVER_ID}' (HSN); got: ${JSON.stringify(clean(value))}`);
  }
  return receiverId;
}

export function validateMemberRow(row: Record<string, unknown>, rowNumber: number): CsvPreviewRow {
  const errors: string[] = [];
  let firstName = "";
  let lastName = "";
  let subscriberId = "";
  let dob = "";
  let gender: "M" | "F" | "U" = "U";

  try {
    firstName = x12Safe(row["First Name"]);
    if (!firstName) throw new ValidationError("First Name is required");
  } catch (error) {
    errors.push(error instanceof Error ? error.message : String(error));
  }

  try {
    lastName = x12Safe(row["Last Name"]);
    if (!lastName) throw new ValidationError("Last Name is required");
  } catch (error) {
    errors.push(error instanceof Error ? error.message : String(error));
  }

  try {
    subscriberId = validateSubscriberId(row["Medicaid Number"]);
  } catch (error) {
    errors.push(error instanceof Error ? error.message : String(error));
  }

  try {
    dob = normalizeDate(row["Birth Date"], "Birth Date");
  } catch (error) {
    errors.push(error instanceof Error ? error.message : String(error));
  }

  try {
    gender = validateGender(row["Gender"]);
  } catch (error) {
    errors.push(error instanceof Error ? error.message : String(error));
  }

  return {
    rowNumber,
    raw: row,
    member:
      errors.length === 0
        ? {
            subscriberId,
            firstName,
            lastName,
            dob,
            gender,
          }
        : undefined,
    errors,
  };
}

export function validate270Options(options: Build270Options): Omit<Build270Options, "environment" | "maxInquiries"> & {
  environment: Environment;
  maxInquiries: number;
} {
  const submitterId = validateSubmitterReceiverId(options.submitterId, "submitter_id");
  const receiverId = validateReceiverId(options.receiverId);
  const providerNpi = validateNpi(options.providerNpi, "provider_npi");
  const providerName = x12Safe(options.providerName);
  if (!providerName) throw new ValidationError("provider_name is required");
  const environment = options.environment === "PROD" ? "PROD" : "TEST";
  const maxInquiries = Number(options.maxInquiries);
  if (!Number.isInteger(maxInquiries) || maxInquiries < 1) {
    throw new ValidationError("max_inquiries must be a positive integer");
  }
  if (environment === "TEST" && maxInquiries > MAX_TEST_INQUIRIES) {
    throw new ValidationError(`MassHealth test files must contain at most ${MAX_TEST_INQUIRIES} inquiries. You requested ${maxInquiries}.`);
  }
  return {
    ...options,
    submitterId,
    providerName,
    providerNpi,
    receiverId,
    serviceDate: normalizeDate(options.serviceDate, "service_date"),
    environment,
    maxInquiries,
  };
}

function controlValues(now: Date) {
  const yy = now.getFullYear().toString().slice(-2);
  const mm = (now.getMonth() + 1).toString().padStart(2, "0");
  const dd = now.getDate().toString().padStart(2, "0");
  const hh = now.getHours().toString().padStart(2, "0");
  const min = now.getMinutes().toString().padStart(2, "0");
  const ss = now.getSeconds().toString().padStart(2, "0");
  const seed = Number(`${dd}${hh}${min}${ss}`);
  return {
    isaDate: `${yy}${mm}${dd}`,
    isaTime: `${hh}${min}`,
    gsDate: `${now.getFullYear()}${mm}${dd}`,
    gsTime: `${hh}${min}`,
    isaControl: String(seed % 1_000_000_000).padStart(9, "0"),
    gsControl: String(seed % 1_000_000_000),
    stControl: String(seed % 10_000).padStart(4, "0"),
    bhtRef: `${now.getFullYear()}${mm}${dd}${hh}${min}${ss}`,
    trnSeed: Number(`${hh}${min}${ss}`),
  };
}

export function build270(members: MemberInquiry[], rawOptions: Build270Options, now = new Date()): string {
  const options = validate270Options(rawOptions);
  const limitedMembers = members.slice(0, options.maxInquiries);
  if (limitedMembers.length === 0) throw new ValidationError("No valid member rows found in CSV");

  const control = controlValues(now);
  const isaSender = options.submitterId.padEnd(15, " ");
  const isaReceiver = options.receiverId.padEnd(15, " ");
  const usageIndicator = options.environment === "TEST" ? "T" : "P";
  const serviceRange = `${options.serviceDate}-${options.serviceDate}`;

  const envelope = [
    [
      "ISA",
      "00",
      "          ",
      "00",
      "          ",
      "ZZ",
      isaSender,
      "ZZ",
      isaReceiver,
      control.isaDate,
      control.isaTime,
      "^",
      "00501",
      control.isaControl,
      "0",
      usageIndicator,
      ":",
    ].join("*"),
    `GS*HS*${x12Safe(options.submitterId)}*${options.receiverId}*${control.gsDate}*${control.gsTime}*${control.gsControl}*X*${TRANSACTION_VERSION}`,
  ];

  const tx = [
    `ST*270*${control.stControl}*${TRANSACTION_VERSION}`,
    `BHT*0022*13*${control.bhtRef}*${control.gsDate}*${control.gsTime}`,
    "HL*1**20*1",
    `NM1*PR*2*${MASSHEALTH_SOURCE_NAME}*****${MASSHEALTH_PI_CODE}*${MASSHEALTH_PI_ID}`,
    "HL*2*1*21*1",
    `NM1*1P*2*${x12Safe(options.providerName)}*****SV*${x12Safe(options.submitterId)}`,
  ];

  limitedMembers.forEach((member, index) => {
    const hlNumber = index + 3;
    const trnValue = `${control.trnSeed}${String(index + 1).padStart(4, "0")}`.slice(0, 30);
    tx.push(
      `HL*${hlNumber}*2*22*0`,
      `TRN*1*${trnValue}*${x12Safe(options.submitterId)}`,
      `NM1*IL*1*${x12Safe(member.lastName).slice(0, 20)}*${x12Safe(member.firstName).slice(0, 15)}****MI*${x12Safe(member.subscriberId)}`,
      `DMG*D8*${member.dob}*${member.gender}`,
      `DTP*291*RD8*${serviceRange}`,
      "EQ*30",
    );
  });

  tx.push(`SE*${tx.length + 1}*${control.stControl}`);

  return [...envelope, ...tx, `GE*1*${control.gsControl}`, `IEA*1*${control.isaControl}`].join("~\n") + "~\n";
}
