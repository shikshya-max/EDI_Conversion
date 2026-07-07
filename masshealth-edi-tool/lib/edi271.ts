export type ParseIssue = {
  segmentIndex: number;
  segment: string;
  message: string;
};

export type Subscriber271 = {
  medicaidNumber: string;
  name: string;
  eligibilityStatus: string;
  planCoverageDetails: string;
  relevantDates: string;
  responseMessages: string;
  traceNumber: string;
};

type MutableSubscriber = {
  medicaidNumber: string;
  lastName: string;
  firstName: string;
  eligibility: string[];
  dates: string[];
  messages: string[];
  traceNumber: string;
};

export type Parse271Result = {
  subscribers: Subscriber271[];
  issues: ParseIssue[];
};

const eligibilityStatus: Record<string, string> = {
  "1": "Active Coverage",
  "2": "Active - Full Risk Capitation",
  "3": "Active - Services Capitated",
  "4": "Active - Services Capitated to Primary Care Physician",
  "5": "Active - Pending Investigation",
  "6": "Inactive",
  "7": "Inactive - Pending Eligibility Update",
  "8": "Inactive - Pending Investigation",
  A: "Co-Insurance",
  B: "Co-Payment",
  C: "Deductible",
  CB: "Coverage Basis",
  D: "Benefit Description",
  E: "Exclusions",
  F: "Limitations",
  G: "Out of Pocket",
  I: "Non-Covered",
  MC: "Managed Care Coordinator",
  R: "Other or Additional Payor",
  S: "Prior Year History",
  U: "Contact Following Entity for Eligibility or Benefit Information",
};

const serviceType: Record<string, string> = {
  "1": "Medical Care",
  "30": "Health Benefit Plan Coverage",
  "33": "Chiropractic",
  "35": "Dental Care",
  "47": "Hospital",
  "48": "Hospital - Inpatient",
  "50": "Hospital - Outpatient",
  "86": "Emergency Services",
  "88": "Pharmacy",
  "98": "Professional Physician Visit - Office",
  AL: "Vision",
  MH: "Mental Health",
  UC: "Urgent Care",
};

const dateQualifier: Record<string, string> = {
  "007": "Effective",
  "096": "Discharge",
  "193": "Period Start",
  "194": "Period End",
  "198": "Completion",
  "290": "Coordination of Benefits",
  "291": "Plan",
  "292": "Benefit",
  "295": "Primary Care Provider",
  "307": "Eligibility",
  "318": "Added",
  "346": "Plan Begin",
  "347": "Plan End",
  "356": "Eligibility Begin",
  "357": "Eligibility End",
  "435": "Admission",
  "472": "Service",
};

function compact(parts: Array<string | undefined>): string {
  return parts.map((part) => (part ?? "").trim()).filter(Boolean).join(" ");
}

function describeEb(elements: string[]): string {
  const eb01 = elements[1] ?? "";
  const eb03 = elements[3] ?? "";
  const eb04 = elements[4] ?? "";
  const eb05 = elements[5] ?? "";
  const eb06 = elements[6] ?? "";
  const eb07 = elements[7] ?? "";
  const eb08 = elements[8] ?? "";

  const parts = [
    eligibilityStatus[eb01] ? `${eligibilityStatus[eb01]} (${eb01})` : eb01 ? `Status ${eb01}` : "",
    eb03 ? `Service ${serviceType[eb03] ?? eb03} (${eb03})` : "",
    eb04 ? `Insurance ${eb04}` : "",
    eb05 ? `Plan ${eb05}` : "",
    eb06 ? `Time period ${eb06}` : "",
    eb07 ? `Amount ${eb07}` : "",
    eb08 ? `Percent ${eb08}` : "",
  ];
  return compact(parts);
}

function describeDtp(elements: string[]): string {
  const qualifier = elements[1] ?? "";
  const format = elements[2] ?? "";
  const value = elements[3] ?? "";
  const label = dateQualifier[qualifier] ?? qualifier;
  return compact([label, format ? `(${format})` : "", value]);
}

function finishSubscriber(subscriber: MutableSubscriber | undefined): Subscriber271 | undefined {
  if (!subscriber) return undefined;
  return {
    medicaidNumber: subscriber.medicaidNumber,
    name: compact([subscriber.firstName, subscriber.lastName]),
    eligibilityStatus: subscriber.eligibility[0] ?? "",
    planCoverageDetails: subscriber.eligibility.join("; "),
    relevantDates: subscriber.dates.join("; "),
    responseMessages: subscriber.messages.join("; "),
    traceNumber: subscriber.traceNumber,
  };
}

export function parse271(rawText: string): Parse271Result {
  const issues: ParseIssue[] = [];
  const subscribers: Subscriber271[] = [];
  let current: MutableSubscriber | undefined;
  let inSubscriberLoop = false;
  let pendingTrace = "";

  const segments = rawText
    .replace(/^\uFEFF/, "")
    .split("~")
    .map((segment) => segment.trim())
    .filter(Boolean);

  if (segments.length === 0) {
    return {
      subscribers: [],
      issues: [{ segmentIndex: 0, segment: "", message: "No X12 segments found. Expected segments separated by ~." }],
    };
  }

  segments.forEach((segment, index) => {
    const elements = segment.split("*");
    const segmentId = elements[0];

    try {
      switch (segmentId) {
        case "HL": {
          const levelCode = elements[3];
          if (levelCode === "22" || levelCode === "23") {
            const finished = finishSubscriber(current);
            if (finished) subscribers.push(finished);
            current = {
              medicaidNumber: "",
              lastName: "",
              firstName: "",
              eligibility: [],
              dates: [],
              messages: [],
              traceNumber: pendingTrace,
            };
            pendingTrace = "";
            inSubscriberLoop = true;
          } else {
            inSubscriberLoop = false;
          }
          break;
        }
        case "TRN": {
          const trace = elements[2] ?? "";
          if (!trace) throw new Error("TRN segment is missing trace number in TRN02.");
          if (current && inSubscriberLoop) current.traceNumber = trace;
          else pendingTrace = trace;
          break;
        }
        case "NM1": {
          if (elements[1] === "IL") {
            if (!current) {
              current = {
                medicaidNumber: "",
                lastName: "",
                firstName: "",
                eligibility: [],
                dates: [],
                messages: [],
                traceNumber: pendingTrace,
              };
            }
            current.lastName = elements[3] ?? "";
            current.firstName = elements[4] ?? "";
            current.medicaidNumber = elements[9] ?? "";
            inSubscriberLoop = true;
          }
          break;
        }
        case "EB": {
          if (!current || !inSubscriberLoop) {
            throw new Error("EB segment found outside a subscriber loop.");
          }
          const description = describeEb(elements);
          current.eligibility.push(description || segment);
          break;
        }
        case "DTP": {
          if (current && inSubscriberLoop) current.dates.push(describeDtp(elements) || segment);
          break;
        }
        case "MSG": {
          if (current && inSubscriberLoop) current.messages.push((elements[1] ?? "").trim());
          break;
        }
        case "AAA": {
          const message = compact(["AAA rejection", elements[3] ? `code ${elements[3]}` : "", elements[4] ? `action ${elements[4]}` : ""]);
          if (current && inSubscriberLoop) current.messages.push(message);
          issues.push({ segmentIndex: index + 1, segment, message });
          break;
        }
        default:
          break;
      }
    } catch (error) {
      issues.push({
        segmentIndex: index + 1,
        segment,
        message: error instanceof Error ? error.message : String(error),
      });
    }
  });

  const finished = finishSubscriber(current);
  if (finished) subscribers.push(finished);

  if (subscribers.length === 0) {
    issues.push({
      segmentIndex: segments.length,
      segment: segments.at(-1) ?? "",
      message: "No subscriber NM1*IL loop found in the 271 file.",
    });
  }

  return { subscribers, issues };
}
