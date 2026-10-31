# VAHAN VLTD Ingestion & Automation Engine

A high-performance bulk ingestion, validation, and automation suite designed for retrofitting Vehicle Location Tracking Device (VLTD) compliance data into the official **Parivahan / VAHAN SLD Fitting Portal** (`vahan.parivahan.gov.in`).

The platform pairs a responsive React frontend with a FastAPI backend and Selenium WebDriver to provide safe, transaction-controlled portal submissions with PrimeFaces AJAX error detection and authoritative application number verification.

---

## Architecture Overview

- **Frontend**: React 18, Vite, Material UI (MUI v5), PapaParse for client-side CSV processing.
- **Backend**: FastAPI, Uvicorn, Pydantic v2 schemas, and Selenium WebDriver.
- **Workflow Pipeline**:
  1. **Upload & Validate**: Schema validation, regex verification, duplicate detection, and error logging.
  2. **Launch Portal**: Spawns an isolated or attached Chrome session with remote debugging enabled.
  3. **Confirm Session Login**: Introspects live portal DOM elements, verifies session cookies, and loads dynamic field mappings.
  4. **On-Demand Services**: Safe dry-run analysis (`Analyze (no submit)`) and single-entry testing (`test a record`).
  5. **Batch Submit**: Sequential transaction submission with live PrimeFaces XML interception and official fitment reference verification.

---

## Prerequisites

Ensure you have the following installed on your machine:

1. **Node.js**: `v18.0.0` or higher (includes `npm`).
   - Verify: `node -v` and `npm -v`
2. **Python**: `3.10` or higher.
   - Verify: `python --version`
3. **Google Chrome**: Latest stable version installed in default path.

---

## Installation

### 1. Clone or Open the Workspace

Open a terminal (e.g. PowerShell or Bash) in the project root directory:

```bash
cd "c:\Users\HP\Documents\CSV Extractor"
```

### 2. Install Frontend Dependencies

From the project root:

```bash
npm install
```

### 3. Install Backend Dependencies

Install the required Python packages using pip:

```bash
python -m pip install -r requirements.txt
```

*(Alternatively, install directly from `backend/requirements.txt`: `python -m pip install -r backend/requirements.txt`)*

The core Python dependencies are:
- `fastapi`
- `uvicorn`
- `pydantic`
- `python-multipart`
- `selenium`

---

## Running the Project

To run the application locally, start both the **Backend API** and the **Frontend App** in separate terminal windows.

### Terminal 1 — Start the Backend API

```powershell
# Navigate into backend directory
cd backend

# Launch FastAPI server with Uvicorn
python -m uvicorn main:app --host 127.0.0.1 --port 8003 --reload
```

The backend API will start at:
- **API Base URL**: `http://127.0.0.1:8003`
- **Interactive Swagger Docs**: `http://127.0.0.1:8003/docs`
- **Health Check**: `http://127.0.0.1:8003/api/health`

> **Note on Ports**: Ensure the backend port matches `API_BASE_URL` in [src/services/vahanApi.js](file:///c:/Users/HP/Documents/CSV%20Extractor/src/services/vahanApi.js). If running on port `8002` or `8003`, keep them consistent between `main:app` and `vahanApi.js`.

---

### Terminal 2 — Start the Frontend Application

```powershell
# From the project root
npm run dev
```

The Vite dev server will launch at:
- **Frontend URL**: `http://localhost:3000`

Open your browser and navigate to `http://localhost:3000`.

---

## Usage Workflow

1. **Upload CSV**:
   - Drag and drop your VLTD CSV file (or use `sample-data.csv` / `sample-vahan-vltd.csv` provided in the project).
   - Review schema validation errors and row status in the preview table.

2. **Launch Portal**:
   - Click the **`Launch Portal`** button.
   - A Chrome window opens with automation controls and navigates to the VAHAN login page.
   - Complete your login / MFA / captcha manually in Chrome and navigate to the **SLD Fitting Details** page.

3. **Confirm Session Login**:
   - Click the **`Confirm session Login`** button.
   - The engine validates active session authentication, discovers all interactive dropdowns and input fields, and presents the field mapping configuration.

4. **Verify Field Mappings**:
   - Inspect the auto-mapped portal target fields (e.g., VLTD Maker, Model, Serial Number, Provider, IMEI, ICC ID, Reg Type, Vehicle Reg No).
   - Adjust presets or custom selectors if needed.

5. **On-Demand Services**:
   - Click the **`On demand services`** dropdown to:
     - **`Analyze(no submit)`**: Performs an in-memory dry-run autofill and produces a field-by-field verification report without persisting data.
     - **`test a record`**: Executes an end-to-end test on Row 2 to confirm modal handling, confirmation dialogs, and response interceptors.

6. **Batch Submission**:
   - Click **`Batch Submit`** to process all valid records sequentially, or select specific rows and choose **`Submit Selected`** from the dropdown.
   - Real-time audit logs track step-by-step progress, server partial AJAX responses, and official fitment references.

---

## Running Tests & Verifications

### Backend Unit Tests

Run all unit tests covering validation, state transactions, error handling, and timeout behavior:

```powershell
python -m unittest discover -s backend
```

### Frontend Build Check

Verify production bundle compilation:

```powershell
npm run build
```

---

## Project Structure

```text
CSV Extractor/
├── backend/
│   ├── main.py                     # FastAPI routes, CORS, and batch coordinator
│   ├── models.py                   # Pydantic v2 data contracts and state enums
│   ├── selenium_worker.py          # Selenium driver, AJAX interceptor, portal DOM automation
│   ├── validator.py                # CSV schema parsing and regex business validation
│   ├── logger_service.py           # Structured logging and audit trail recorder
│   ├── requirements.txt            # Python dependencies
│   └── test_*.py                   # Backend test suites
├── src/
│   ├── components/                 # Shared UI elements (Navigation, Error boundaries, Modals)
│   ├── context/                    # React Context (CsvContext, VahanAutomationContext)
│   ├── pages/
│   │   └── ExtractPage.jsx         # Primary VAHAN automation dashboard and controls
│   ├── services/
│   │   └── vahanApi.js             # REST API bridge to FastAPI backend
│   ├── App.jsx                     # Route definitions
│   └── main.jsx                    # React application entry point
├── sample-data.csv                 # Sample VLTD test dataset
├── sample-vahan-vltd.csv           # Alternative VLTD test dataset
├── package.json                    # Node dependencies and scripts
├── vite.config.js                  # Vite configuration (port 3000)
├── requirements.txt                # Root Python dependencies
└── README.md                       # Installation and operational documentation
```

---

## Troubleshooting

- **Backend Offline in UI**: Check that the Uvicorn server is running on the expected port (default `8003` in `src/services/vahanApi.js`). Verify `http://127.0.0.1:8003/api/health` returns `{"status":"ok"}`.
- **Port In Use Error**: If port `8003` or `3000` is already in use, stop conflicting processes or adjust the port flag in Uvicorn (`--port <port>`) and in `vahanApi.js`.
- **Chrome Not Opening**: Ensure Google Chrome is installed and updated. The worker automatically configures compatible Selenium Chrome options and remote debugging ports.

