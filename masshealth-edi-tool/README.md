# MassHealth EDI Eligibility Tool

Client-side Next.js app for:

- CSV to X12 5010 270 eligibility inquiry generation
- X12 5010 271 eligibility response parsing to Excel

No API routes are used for file processing. CSV, EDI, and Excel data are handled in browser memory only and downloads are created with `Blob` plus `<a download>`.

## Run locally

```bash
npm install
npm run dev
```

## Build for Vercel/static export

```bash
npm run build
```

The app uses `output: "export"` and can be hosted as a static/client-rendered app.
