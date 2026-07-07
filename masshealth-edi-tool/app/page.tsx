"use client";

import Papa from "papaparse";
import * as XLSX from "xlsx";
import { useMemo, useState } from "react";
import {
  build270,
  MAX_TEST_INQUIRIES,
  MASSHEALTH_RECEIVER_ID,
  REQUIRED_COLUMNS,
  validate270Options,
  validateMemberRow,
} from "../lib/edi270";
import type { CsvPreviewRow, Environment } from "../lib/edi270";
import { parse271 } from "../lib/edi271";
import type { ParseIssue, Subscriber271 } from "../lib/edi271";

type Tab = "generate" | "parse";

type GeneratorForm = {
  receiverId: string;
  serviceDate: string;
  environment: Environment;
  maxInquiries: number;
  skipInvalidRows: boolean;
};

const today = () => new Date().toISOString().slice(0, 10);
const PROVIDER_CONFIG = {
  submitterId: "110189969A",
  providerName: "HOME CARE & MORE LLC",
  providerNpi: "1578090817",
};

const initialForm: GeneratorForm = {
  receiverId: MASSHEALTH_RECEIVER_ID,
  serviceDate: today(),
  environment: "TEST",
  maxInquiries: MAX_TEST_INQUIRIES,
  skipInvalidRows: false,
};

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function DropZone({
  label,
  accept,
  onFile,
}: {
  label: string;
  accept: string;
  onFile: (file: File) => void;
}) {
  const [dragging, setDragging] = useState(false);

  return (
    <label
      className={`dropzone ${dragging ? "dragging" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        const file = event.dataTransfer.files.item(0);
        if (file) onFile(file);
      }}
    >
      <span>{label}</span>
      <input
        type="file"
        accept={accept}
        onChange={(event) => {
          const file = event.target.files?.item(0);
          if (file) onFile(file);
          event.currentTarget.value = "";
        }}
      />
    </label>
  );
}

function ErrorList({ errors }: { errors: string[] }) {
  if (errors.length === 0) return <span className="ok">Valid</span>;
  return (
    <ul className="inlineErrors">
      {errors.map((error, index) => (
        <li key={`${error}-${index}`}>{error}</li>
      ))}
    </ul>
  );
}

function RefreshIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="refreshIcon">
      <path d="M20 6v5h-5" />
      <path d="M4 18v-5h5" />
      <path d="M18.4 9A7 7 0 0 0 6.1 6.7L4 9" />
      <path d="M5.6 15A7 7 0 0 0 17.9 17.3L20 15" />
    </svg>
  );
}

export default function Home() {
  const [tab, setTab] = useState<Tab>("generate");
  const [form, setForm] = useState<GeneratorForm>(initialForm);
  const [csvRows, setCsvRows] = useState<CsvPreviewRow[]>([]);
  const [csvError, setCsvError] = useState("");
  const [sourceFileName, setSourceFileName] = useState("");
  const [parserRows, setParserRows] = useState<Subscriber271[]>([]);
  const [parserIssues, setParserIssues] = useState<ParseIssue[]>([]);
  const [parserFileName, setParserFileName] = useState("");

  const validRows = useMemo(() => csvRows.filter((row) => row.member), [csvRows]);
  const invalidRows = useMemo(() => csvRows.filter((row) => row.errors.length > 0), [csvRows]);
  const effectiveMaxInquiries = form.environment === "TEST" ? form.maxInquiries : Math.max(validRows.length, 1);

  const formErrors = useMemo(() => {
    try {
      validate270Options({ ...form, ...PROVIDER_CONFIG, maxInquiries: effectiveMaxInquiries });
      return [];
    } catch (error) {
      return [error instanceof Error ? error.message : String(error)];
    }
  }, [effectiveMaxInquiries, form]);

  const hasGenerateState = csvRows.length > 0 || csvError.length > 0 || sourceFileName.length > 0;
  const hasParserState = parserRows.length > 0 || parserIssues.length > 0 || parserFileName.length > 0;

  function clearGenerateState() {
    setCsvRows([]);
    setCsvError("");
    setSourceFileName("");
  }

  function clearParserState() {
    setParserRows([]);
    setParserIssues([]);
    setParserFileName("");
  }

  function readCsv(file: File) {
    setSourceFileName(file.name);
    setCsvError("");
    setCsvRows([]);

    Papa.parse<Record<string, unknown>>(file, {
      header: true,
      skipEmptyLines: true,
      transformHeader: (header) => header.trim().replace(/^\uFEFF/, ""),
      complete: (result) => {
        const fields = result.meta.fields ?? [];
        const missing = REQUIRED_COLUMNS.filter((column) => !fields.includes(column));
        if (missing.length > 0) {
          setCsvError(`CSV missing required columns: ${missing.join(", ")}`);
          return;
        }
        const rows = result.data.map((row, index) => validateMemberRow(row, index + 2));
        setCsvRows(rows);
        if (result.errors.length > 0) {
          setCsvError(result.errors.map((error) => `Row ${error.row ?? "?"}: ${error.message}`).join("; "));
        }
      },
      error: (error) => {
        setCsvError(error.message);
      },
    });
  }

  function generate270() {
    const usableRows = form.skipInvalidRows ? validRows : csvRows;
    const members = usableRows.map((row) => row.member).filter((member): member is NonNullable<typeof member> => Boolean(member));

    if (!form.skipInvalidRows && invalidRows.length > 0) {
      setCsvError("Fix invalid rows or enable Skip invalid rows before generating.");
      return;
    }

    try {
      const edi = build270(members, { ...form, ...PROVIDER_CONFIG, maxInquiries: effectiveMaxInquiries });
      const filenameBase = sourceFileName.replace(/\.[^.]+$/, "") || "masshealth_270";
      downloadBlob(`${filenameBase}_270.txt`, new Blob([edi], { type: "text/plain;charset=utf-8" }));
      setCsvError("");
    } catch (error) {
      setCsvError(error instanceof Error ? error.message : String(error));
    }
  }

  function read271(file: File) {
    setParserFileName(file.name);
    setParserRows([]);
    setParserIssues([]);

    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result ?? "");
      const result = parse271(text);
      setParserRows(result.subscribers);
      setParserIssues(result.issues);
    };
    reader.onerror = () => {
      setParserIssues([{ segmentIndex: 0, segment: file.name, message: "Unable to read file." }]);
    };
    reader.readAsText(file);
  }

  function downloadExcel() {
    const worksheet = XLSX.utils.json_to_sheet(
      parserRows.map((row) => ({
        "Medicaid Number": row.medicaidNumber,
        Name: row.name,
        "Eligibility Status": row.eligibilityStatus,
        "Plan/Coverage details": row.planCoverageDetails,
        "Relevant dates": row.relevantDates,
        "Response messages": row.responseMessages,
        "Trace Number": row.traceNumber,
      })),
    );
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "271 Response");
    const output = XLSX.write(workbook, { type: "array", bookType: "xlsx" });
    const filenameBase = parserFileName.replace(/\.[^.]+$/, "") || "masshealth_271";
    downloadBlob(`${filenameBase}_parsed.xlsx`, new Blob([output], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
  }

  return (
    <main className="shell">
      <header className="header">
        <div>
          <p className="eyebrow">Sewa Home Care</p>
          <h1>Eligibility File Tool</h1>
          <p>Generate MassHealth inquiry files and review response files in one place.</p>
        </div>
        <div className="environmentMenu" aria-label="Environment">
          <span>Mode</span>
          <div className="segmented">
            <button
              className={form.environment === "TEST" ? "active" : ""}
              onClick={() => setForm({ ...form, environment: "TEST", maxInquiries: Math.min(form.maxInquiries, MAX_TEST_INQUIRIES) })}
              type="button"
            >
              Test
            </button>
            <button
              className={form.environment === "PROD" ? "active" : ""}
              onClick={() => setForm({ ...form, environment: "PROD" })}
              type="button"
            >
              Production
            </button>
          </div>
        </div>
      </header>

      <nav className="tabs" aria-label="Tool sections">
        <button className={tab === "generate" ? "active" : ""} onClick={() => setTab("generate")}>
          Generate 270
        </button>
        <button className={tab === "parse" ? "active" : ""} onClick={() => setTab("parse")}>
          Parse 271
        </button>
      </nav>

      {tab === "generate" ? (
        <section className="panel">
          <div className="sectionHeader">
            <div>
              <h2>Generate a 270 inquiry</h2>
              <p>Upload the member CSV, review the rows, then download the ready-to-submit file.</p>
            </div>
            <button className="clearButton" type="button" onClick={clearGenerateState} disabled={!hasGenerateState} title="Clear uploaded CSV and preview">
              <RefreshIcon />
              <span>Clear</span>
            </button>
          </div>

          <div className="grid compactGrid">
            <label>
              Receiver
              <select value={form.receiverId} onChange={(event) => setForm({ ...form, receiverId: event.target.value })}>
                <option value="DMA7384">DMA7384 - MassHealth</option>
                <option value="HSN3644">HSN3644 - HSN</option>
              </select>
            </label>
            <label>
              Service date
              <input type="date" value={form.serviceDate} onChange={(event) => setForm({ ...form, serviceDate: event.target.value })} />
            </label>
            {form.environment === "TEST" && (
              <label>
                Test batch size
                <input
                  type="number"
                  min={1}
                  max={MAX_TEST_INQUIRIES}
                  value={form.maxInquiries}
                  onChange={(event) => setForm({ ...form, maxInquiries: Number(event.target.value) })}
                />
              </label>
            )}
            <label className="checkbox">
              <input
                type="checkbox"
                checked={form.skipInvalidRows}
                onChange={(event) => setForm({ ...form, skipInvalidRows: event.target.checked })}
              />
              Skip invalid rows
            </label>
          </div>

          <DropZone label="Drop CSV here or choose file" accept=".csv,text/csv" onFile={readCsv} />

          {(csvError || formErrors.length > 0) && (
            <div className="errorBox">
              {[...formErrors, csvError].filter(Boolean).map((error, index) => (
                <div key={`${error}-${index}`}>{error}</div>
              ))}
            </div>
          )}

          {csvRows.length > 0 && (
            <>
              <div className="summary">
                <span>{sourceFileName}</span>
                <span>{validRows.length} valid</span>
                <span>{invalidRows.length} invalid</span>
                <span>{Math.min(validRows.length, effectiveMaxInquiries)} included</span>
              </div>
              <div className="tableWrap">
                <table>
                  <thead>
                    <tr>
                      <th>Row</th>
                      <th>Medicaid Number</th>
                      <th>Last Name</th>
                      <th>First Name</th>
                      <th>DOB</th>
                      <th>Gender</th>
                      <th>Validation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {csvRows.map((row) => (
                      <tr key={row.rowNumber} className={row.errors.length ? "badRow" : ""}>
                        <td>{row.rowNumber}</td>
                        <td>{row.member?.subscriberId ?? String(row.raw["Medicaid Number"] ?? "")}</td>
                        <td>{row.member?.lastName ?? String(row.raw["Last Name"] ?? "")}</td>
                        <td>{row.member?.firstName ?? String(row.raw["First Name"] ?? "")}</td>
                        <td>{row.member?.dob ?? String(row.raw["Birth Date"] ?? "")}</td>
                        <td>{row.member?.gender ?? String(row.raw["Gender"] ?? "")}</td>
                        <td>
                          <ErrorList errors={row.errors} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button className="primary" disabled={validRows.length === 0 || formErrors.length > 0} onClick={generate270}>
                Generate & Download EDI
              </button>
            </>
          )}
        </section>
      ) : (
        <section className="panel">
          <div className="sectionHeader">
            <div>
              <h2>Review a 271 response</h2>
              <p>Upload the MassHealth response file, check the preview, then download the spreadsheet.</p>
            </div>
            <button className="clearButton" type="button" onClick={clearParserState} disabled={!hasParserState} title="Clear uploaded response and preview">
              <RefreshIcon />
              <span>Clear</span>
            </button>
          </div>
          <DropZone label="Drop 271 EDI text here or choose file" accept=".txt,.edi,text/plain" onFile={read271} />

          {parserIssues.length > 0 && (
            <div className="errorBox">
              {parserIssues.map((issue, index) => (
                <div key={`${issue.segmentIndex}-${index}`}>
                  Segment {issue.segmentIndex}: {issue.message}
                </div>
              ))}
            </div>
          )}

          {parserRows.length > 0 && (
            <>
              <div className="summary">
                <span>{parserFileName}</span>
                <span>{parserRows.length} member row{parserRows.length === 1 ? "" : "s"}</span>
              </div>
              <div className="tableWrap">
                <table>
                  <thead>
                    <tr>
                      <th>Medicaid Number</th>
                      <th>Name</th>
                      <th>Eligibility Status</th>
                      <th>Plan/Coverage details</th>
                      <th>Relevant dates</th>
                      <th>Messages</th>
                      <th>Trace Number</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parserRows.map((row, index) => (
                      <tr key={`${row.medicaidNumber}-${row.traceNumber}-${index}`}>
                        <td>{row.medicaidNumber}</td>
                        <td>{row.name}</td>
                        <td>{row.eligibilityStatus}</td>
                        <td>{row.planCoverageDetails}</td>
                        <td>{row.relevantDates}</td>
                        <td>{row.responseMessages}</td>
                        <td>{row.traceNumber}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button className="primary" onClick={downloadExcel}>
                Download Excel
              </button>
            </>
          )}
        </section>
      )}
    </main>
  );
}
