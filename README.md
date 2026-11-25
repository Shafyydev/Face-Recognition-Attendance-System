# Face Recognition Attendance System

**A desktop-based student attendance management system powered by real-time face recognition, automated attendance tracking, SMS notifications, and an interactive dark-themed dashboard.**

[**View Source Code →**](https://github.com/Shafyydev/face-recognition-attendance-system)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-4.8+-5C3EE8?logo=opencv&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?logo=sqlite&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-1.26-013243?logo=numpy&logoColor=white)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Overview

The **Face Recognition Attendance System** (configured for **St. Joseph's College of Arts & Science (Autonomous), Cuddalore**) is a local desktop and web application that automates student attendance using webcam-based facial recognition.

Built with Python, OpenCV, `face_recognition` (`dlib`), Flask, SQLAlchemy/SQLite, and `pywebview`, the system isolates heavy face-recognition inference in a dedicated background process while serving a responsive live dashboard with real-time bounding boxes, voice feedback, time-cutoff rules, admin-authenticated manual overrides, and multi-provider SMS notifications.

---

## Application Preview

![Face Recognition Attendance System Dashboard](face_recognition_attendance_system%20preview.png)

*The dashboard features an animated startup splash screen, live camera stream with HUD recognition banners, real-time attendance metrics, department breakdowns, date-scoped audit/activity logs, and student management.*

---

## Key Features

### Real-Time Face Recognition & Camera Feedback
- **Multi-Process Recognition Worker** — Runs frame encoding and matching in an isolated child process (`face_utils/recognition_worker.py`) to keep the UI and video preview smooth.
- **Multi-Frame Confirmation Engine** — Requires candidate matches to satisfy a maximum face distance (`0.50`), minimum identity margin (`0.08`), and 3 consecutive processed frames (`RecognitionDecisionEngine`) before committing attendance.
- **Status-Coded Video Overlays & HUD Banner** — Draws live bounding boxes (`Present`, `Confirming`, `(Already Present)`, `(Already Absent)`, `Absent`, and orange `No Attendance Today` on Sundays) alongside a floating camera recognition HUD card in the dashboard.
- **Text-to-Speech (TTS) Announcements** — Non-blocking daemon worker (`tts_service.py` using `pyttsx3`) announces attendance results aloud without blocking the video pipeline.

### Attendance Rules, Scheduling & Date Management
- **Automated Time Cutoffs**:
  - Before **8:30 AM** → `on_time`
  - **8:30 AM – 9:30 AM** → `late` (triggers late-arrival SMS alert)
  - After **9:30 AM** → `absent` (camera marks absent & sends absent alert)
- **Automated Daily Absentee Scheduler** — Background scheduler in `notification_service.py` checks for unmarked active students after the **9:30 AM** cutoff, creates `absent` records, dispatches SMS alerts, and can also be triggered manually via `/api/absentee/trigger`.
- **Sunday / Non-Working Day Handling** — Automatically records camera check-ins as `no_attendance`, disables manual status overrides, and suppresses automated absentee runs and SMS alerts on Sundays.
- **Historical Date Switching & Activity Isolation** — Custom dashboard date picker (`/api/set_attendance_date`) reconciles past dates, filters attendance/statistics/activity logs per date, and supports date-specific record clearing (`/api/clear_today`).

### Student Enrollment & Management
- **5-Sample Guided Registration** (`/register`) — Validates and captures 5 webcam face samples using an independent Haar cascade face-positioning box (`data/models/haarcascade_frontalface_default.xml`), temporarily holding dashboard attendance marking while the registration page is open.
- **Persistent 128-D Embeddings** — Stores per-student 128-dimensional embedding JSON files in `data/face_embeddings/` and reference photos in `data/known_faces/`.
- **Student Manager & Reporting** — Search, edit, and delete students, filter attendance by status (`All`, `On Time`, `Late`, `Absent`) or department, export CSV files (attendance & student rosters), and print formatted reports.

### Security, Notifications & Reliability
- **Admin-Authenticated Manual Overrides** — Changing a student's status manually (`POST /api/attendance/manual`) requires verified `Admin` credentials (`/api/admin/verify`), writes an audit entry to `AdminOverrideLog`, and dispatches correction, late, or absent SMS alerts as needed.
- **Multi-Provider SMS Gateway & Auto-Retry** — Supports `mock`, `android` / `android_gateway` / `android_sms` (with automatic LAN subnet discovery), `smsgate` / `smsgate_cloud`, `fast2sms`, `twilio`, and `generic` HTTP providers, backed by a 30-second background retry queue and a circuit breaker (`middleware/circuit_breaker.py`).
- **Middleware & API Gateway** — Includes sliding-window rate limiting (`middleware/rate_limiter.py`), TTL response caching with automatic invalidation (`middleware/cache.py`), service discovery registry (`middleware/service_discovery.py`), request ID/timing/security headers, optional API key enforcement, and a `/api/health` endpoint (`gateway/api_gateway.py`).

---

## Getting Started

### Prerequisites

- **Python**: Version **3.12** (tested with Python 3.12.10 and `dlib` 19.24+)
- **Webcam**: Standard USB or integrated webcam
- **C++ Build Tools**: Visual Studio C++ Build Tools + CMake on Windows (or install a prebuilt `dlib` wheel for Python 3.12)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Shafyydev/face-recognition-attendance-system.git
   cd face-recognition-attendance-system
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables (optional):**
   ```bash
   copy .env.example .env    # Windows
   cp .env.example .env      # macOS/Linux
   ```

5. **Bootstrap an Admin Account (recommended for manual overrides):**
   Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` in your environment (or `.env` when loaded before starting `app.py`) so an initial active `Admin` user is created automatically on startup.

### Running the Application

- **Desktop Window (Recommended):**
  ```bash
  python launcher.py
  ```
  Starts the Flask server, verifies `/api/status` readiness, and opens the dashboard inside a `pywebview` desktop window with native file-save dialog support.

- **Web Browser (Development Mode):**
  ```bash
  python app.py
  ```
  Starts the Flask server on port `5000` and automatically opens `http://127.0.0.1:5000` in your default browser.

---

## Environment Configuration

The following variables are read by the application modules (`.env.example` provides a starter template):

| Variable | Description | Default |
|---|---|---|
| `ATTENDANCE_DB_PATH` | Path to the SQLite attendance database | `attendance.db` (next to app/exe) |
| `COLLEGE_NAME` | Institution name shown in SMS alerts and reports | `St.Joseph's College of Arts & Science (Autonomous) - Cuddalore` |
| `ADMIN_USERNAME` | Initial admin username bootstrapped on startup if not present | *(unset)* |
| `ADMIN_PASSWORD` | Initial admin password hashed and stored in `admins` table | *(unset)* |
| `SMS_ENABLED` | Enable or disable automated SMS alerts (`true` / `false`) | `true` |
| `SMS_PROVIDER` | Provider (`mock`, `android`, `smsgate_cloud`, `fast2sms`, `twilio`, `generic`) | `mock` |
| `SMS_API_URL` | Gateway endpoint URL (auto-discovered on LAN for Android SMS Gate if blank) | `http://192.168.1.100:8080` |
| `SMS_API_KEY` | API key or `username:password` (for `smsgate_cloud`) | *(empty)* |
| `SMS_SENDER_ID` | Registered sender ID header | `STJOSEPH` |
| `SMS_DEVICE_ID` | Optional device ID for `smsgate_cloud` | *(empty)* |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID (when `SMS_PROVIDER=twilio`) | *(empty)* |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token (when `SMS_PROVIDER=twilio`) | *(empty)* |
| `TWILIO_FROM_NUMBER` | Twilio sender phone number | *(empty)* |
| `RATE_LIMIT_ENABLED` | Enable in-memory rate limiting (`true` / `false`) | `true` |
| `CACHE_ENABLED` | Enable TTL API response caching (`true` / `false`) | `true` |
| `API_GATEWAY_KEY` | Shared key checked via `X-API-Key` header or `api_key` query param | *(empty)* |
| `API_GATEWAY_AUTH_REQUIRED` | Enforce `API_GATEWAY_KEY` on `/api/*` routes (`true` / `false`) | `false` |

---

## Recognition & Cutoff Configuration

| Parameter | Configuration |
|---|---|
| Face encoding | 128-dimensional embeddings (`EmbeddingEncoder`) |
| Live face detection | HOG-based detection (`face_recognition`) |
| Registration preview box | Haar cascade (`haarcascade_frontalface_default.xml`) |
| Frame sampling rate | Every `3`rd frame (`PROCESS_EVERY_N_FRAMES = 3`) |
| Maximum match distance | `0.50` |
| Minimum identity margin | `0.08` |
| Confirmation consistency | `3` consecutive processed frames (`reset_after_misses = 2`) |
| Late threshold | After `08:30 AM` |
| Absent cutoff & scheduler | After `09:30 AM` |
| Registration samples | `5` validated webcam frames |
| Database engine | SQLite with WAL journal mode (`NullPool`, 30s busy timeout) |
| Embedding storage | Per-student JSON files (`data/face_embeddings/<ID>.json`) |

---

## API Overview

| Category | Endpoints |
|---|---|
| **Pages** | `GET /`, `GET /register` |
| **Video & Capture** | `GET /video_feed`, `GET /registration_feed`, `GET /api/capture_frame` |
| **System & Health** | `GET /api/status`, `GET /api/health`, `GET /api/recognition_status` |
| **Attendance & Stats** | `GET /api/attendance`, `GET /api/stats`, `GET /api/activity`, `POST /api/attendance/manual`, `GET/POST /api/set_attendance_date`, `POST /api/clear_today`, `POST /api/absentee/trigger`, `GET /api/attendance/export` |
| **Students & Admin** | `GET /api/students`, `POST /api/register`, `PUT /api/students/<student_id>`, `DELETE /api/students/<student_id>`, `POST /api/admin/verify` |

---

## Technology Stack

| Layer | Technologies |
|---|---|
| **Backend & API** | Python 3.12, Flask 3.0, Flask-CORS, Werkzeug Security, SQLAlchemy 2.0, SQLite (WAL) |
| **Computer Vision** | OpenCV, `face_recognition`, `dlib`, NumPy, Pillow |
| **Desktop & Audio** | `pywebview`, `pyttsx3` (SAPI5 / TTS daemon), Windows `multiprocessing` |
| **Resilience & Gateway** | Custom Rate Limiter, TTL Response Cache, Circuit Breaker, Service Discovery, API Gateway |
| **Packaging & Ops** | PyInstaller (`AttendanceSystem.spec`), Inno Setup, Docker, Nginx, Kubernetes, GitHub Actions |

---

## Project Structure

```text
attendance_system/
├── app.py                          # Flask server, camera loop, REST API & date reconciliation
├── launcher.py                     # Desktop app entry point via pywebview
├── notification_service.py         # Multi-provider SMS alerts, retry worker & 9:30 AM absentee scheduler
├── tts_service.py                  # Asynchronous text-to-speech announcement worker
├── check_db.py                     # CLI inspection utility for development database
├── check_packaged_db.py            # CLI inspection utility for packaged executable database
├── AttendanceSystem.spec           # PyInstaller specification for Windows EXE packaging
├── build.bat                       # Data-safe Windows executable build script
├── AttendanceSystemSetup.iss       # Inno Setup Windows installer script
├── Dockerfile                      # Multi-stage Python 3.12 Docker build
├── docker-compose.yml              # App + optional Nginx compose stack
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment configuration template
├── SECURITY.md                     # Security policy and biometric privacy guidelines
├── .github/workflows/ci-cd.yml     # Lint, Windows unittest suite, Docker build & release pipeline
├── database/
│   └── models.py                   # SQLAlchemy models (Student, Attendance, ActivityLog, Admin, AdminOverrideLog)
├── face_utils/
│   ├── attendance_marker.py        # Multi-frame attendance tracking, cutoffs, Sunday & hold logic
│   ├── decision_engine.py          # Distance, margin & consecutive-frame confirmation engine
│   ├── embedding_encoder.py        # 128-D face embedding extractor
│   ├── face_embedding_store.py     # Persistent per-student JSON embedding store
│   └── recognition_worker.py       # Isolated multiprocessing recognition worker
├── gateway/
│   └── api_gateway.py              # Request tracing, security headers, optional API key auth & /api/health
├── middleware/
│   ├── cache.py                    # In-memory TTL response cache & invalidation helpers
│   ├── circuit_breaker.py          # Circuit breaker for external SMS gateway protection
│   ├── rate_limiter.py             # Thread-safe sliding-window endpoint rate limiter
│   └── service_discovery.py        # Internal/LAN service registry and health tracker
├── templates/
│   ├── dashboard.html              # Dark dashboard UI, startup splash screen & HUD overlays
│   └── register.html               # 5-sample guided student enrollment UI
├── static/
│   ├── college_logo.jpg            # Institution logo used in splash screen and header
│   └── app_icon.png                # Transparent 256x256 application icon asset
├── data/
│   └── models/
│       └── haarcascade_frontalface_default.xml  # Bundled Haar cascade for registration preview
├── tools/
│   └── backup_db.py                # Online SQLite WAL-safe backup utility with rotation
├── tests/                          # Unit & integration test suite (38 tests)
├── nginx/nginx.conf                # Optional reverse proxy configuration
└── k8s/                            # Kubernetes manifests (configmap, deployment, service, pvc, ingress)
```

---

## Testing, Maintenance & Packaging

### Running the Test Suite
Run all 38 unit and integration tests (covering decision engine matching, date handling, late/absent SMS dispatch, Sunday mode, and audit fixes):
```bash
python -m unittest discover tests
```

### Database Utilities
- **Inspect development database:**
  ```bash
  python check_db.py
  ```
- **Inspect packaged build database (`dist/AttendanceSystem/attendance.db`):**
  ```bash
  python check_packaged_db.py
  ```
- **Create an online SQLite backup (keeps latest 10 snapshots in `backups/`):**
  ```bash
  python tools/backup_db.py
  ```

### Building the Windows Executable & Docker Image
- **Windows EXE (PyInstaller):**
  Run `build.bat` (or `pyinstaller AttendanceSystem.spec --noconfirm`) to output `dist/AttendanceSystem/AttendanceSystem.exe` with bundled templates, static assets, middleware/gateway packages, OpenCV/dlib models, and Haar cascade XML. Note that `build.bat` removes `dist\AttendanceSystem` before rebuilding, so back up any runtime `dist\AttendanceSystem\attendance.db` or `data\` first if you run directly from `dist\`.
- **Docker Compose:**
  ```bash
  docker compose up -d
  ```
  *(Webcam passthrough via `/dev/video0` applies on Linux hosts; use the native launcher or EXE on Windows for camera access.)*

---

## Privacy and Security

This application processes biometric embeddings and student attendance data. Review [SECURITY.md](SECURITY.md) and apply appropriate institutional safeguards before campus deployment:

- Obtain informed consent and institutional authorization before collecting facial data.
- Protect `attendance.db`, `data/face_embeddings/`, `data/known_faces/`, and `.env` secrets with strict host access controls.
- Establish data retention and deletion policies (deleting a student from the UI removes their database records, embeddings, and reference image).
- Do not treat automated facial recognition as infallible or assume the configured thresholds provide anti-spoofing / liveness verification.

---

## Potential Improvements

- Liveness detection and anti-spoofing safeguards (such as blink or head-pose verification)
- Startup session-wide admin lock screen preceding the splash screen
- Evaluation of recognition accuracy under varying lighting and webcam hardware
- Role-based access control and multi-operator audit views in the UI
- Encrypted biometric embedding storage at rest

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Repository

**[Explore the Face Recognition Attendance System on GitHub →](https://github.com/Shafyydev/face-recognition-attendance-system)**

---

**Developed by Mohammed Shafiullah N**
