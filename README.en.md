# WenShu · Batch Intent Classification & Summarization Workbench for Customer Service

[简体中文](README.md) | [English](README.en.md)

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-0078D4)
![Python](https://img.shields.io/badge/Python-3.13-3776AB)
![Vue](https://img.shields.io/badge/Vue-3-42B883)
![Tests](https://img.shields.io/badge/tests-200%20backend%20%2B%208%20e2e-brightgreen)

WenShu is a local-first batch text workbench for customer-service teams. Drop call transcripts, tickets, or follow-up records into the app; run **intent classification** or **text summarization** row by row with any OpenAI-compatible model; review and correct the results; export to Excel or CSV. Your files and API keys stay on your machine.

<p align="center">
  <img src="docs/assets/screenshots/home.jpg" alt="WenShu home: drop a customer-service file to start intent classification or summarization" width="880">
</p>

## Why WenShu

Customer-service agents, QA reviewers, and operations teams read and label a lot of text every day. The bottleneck is rarely the model — it is the lack of a practical tool that a frontline user can trust, operate, and audit.

WenShu focuses on four problems:

- **Too much to read**: thousands of rows, reviewed one by one, is slow and exhausting.
- **Inconsistent labels**: different reviewers classify the same issue differently.
- **Summaries don't scale**: long-text summaries are manual, slow, and easy to miss key points.
- **No audit trail**: corrections leave no trace, and exporting still requires manual spreadsheet work.

## Features

- **Intent classification**: batch-classify against categories defined in your prompt, with confidence, reasoning, category stats, and a metro-style line map.
- **Text summarization**: segment long text, summarize each chunk, merge results; edit the summary while keeping the model's original.
- **Human review**: intent corrections are limited to categories defined in the prompt; before/after values are visible; reviewed markers; exported files include the original value.
- **Prompt workbench**: built-in classification and summarization templates; edit, test-run, version history, restore defaults.
- **Bring your own model**: any OpenAI-compatible endpoint; a built-in demo model works without an API key.
- **Local-first**: listens on `127.0.0.1` only, single user, no login; API keys are encrypted with a local key; no telemetry.

<p align="center">
  <img src="docs/assets/screenshots/select-columns.jpg" alt="Select data: click a column header to choose the text columns to process" width="860">
</p>

## Quick Start

### Option 1: Portable build (recommended for users)

1. Open [Releases](https://github.com/futureYYY/wenshu-workbench/releases) and download the latest `WenShu.zip`.
2. Extract it anywhere (Chinese characters and spaces in the path are supported).
3. Double-click `WenShu.exe`.

Python and Node are **not** required. On first launch WenShu creates a `data` folder next to the executable. The built-in demo model lets you try the full workflow; to use a real model, fill in the endpoint, model name, and API key on the Models page.

### Option 2: From source (for reading or changing the code)

Requires **Python 3.13**. **Node.js 24** is only needed when you change frontend source.

```bat
git clone https://github.com/futureYYY/wenshu-workbench.git
cd wenshu-workbench
启动文枢.bat
```

The first launch creates `backend\.venv`, installs dependencies, and builds the UI. For separate frontend/backend development, run `scripts\dev.bat` (backend on 18765, frontend on 5173).

## How It Works

1. **Upload** a `csv`, `xlsx`, `xls`, `txt`, or `md` file (or paste text).
2. **Select columns**: click the header of the text column(s) to process; multiple columns are joined.
3. **Configure**: choose the task, prompt, model, concurrency, and row limit.
4. **Run**: watch progress, parallel tracks, the result grid, and the line map.
5. **Review & export**: correct rows, mark them reviewed, export xlsx/csv with corrected values and the original values.

<p align="center">
  <img src="docs/assets/screenshots/results.jpg" alt="Results page with line map, result grid, and review filter" width="860">
</p>

<p align="center">
  <img src="docs/assets/screenshots/review.jpg" alt="Human review: correct an intent and see the original value" width="860">
</p>

## Model Configuration

WenShu only requires an OpenAI-compatible `/chat/completions` endpoint:

- Configure `base_url`, model name, and API key on the Models page;
- Temperature, max output, context window, timeout, concurrency, JSON mode, and extra headers/body are configurable;
- API keys are encrypted locally and only shown as a mask;
- The built-in demo model lets you try the app without a real model (its output is simulated).

You can also place a default custom model in `backend/models.local.json` (not committed; see `backend/models.local.json.example`). That file contains a plaintext key — keep it on your own machine and never commit it.

## Who It Is For

- Customer-service agents organizing call transcripts and follow-up text;
- QA and operations teams standardizing intent labels and review;
- Individuals and small teams that need batch text processing.

## Privacy & Security

- The backend binds to `127.0.0.1` only;
- Files, results, and keys stay in your local data directory;
- API keys are encrypted with a local `secret.key`;
- No telemetry or usage collection;
- Model requests go only to the endpoint you configure — use a model service that meets your compliance requirements;
- The repository contains no real API keys; all sample data is fictional.

## Tech Stack

- Backend: Python 3.13, FastAPI, SQLAlchemy 2 (async), SQLite
- Frontend: Vue 3, Vite, TypeScript, Tailwind CSS, Reka UI
- Packaging: PyInstaller; the portable build bundles its own runtime

See [`docs/`](docs/) for requirements, architecture, database, API, prompts, UI, packaging, and acceptance.

## Roadmap

- [ ] More task types beyond classification
- [ ] Prompt template sharing and import
- [ ] Batch job queues and finer rate limiting
- [ ] Better accessibility and narrow-screen layouts

Issues with real use cases are welcome.

## Contributing

Issues, pull requests, prompt templates, and feedback are welcome:

1. Fork the repository and create a branch from `main`;
2. Before submitting, run `backend\.venv\Scripts\python.exe -m pytest backend\tests -q`, `npm run typecheck`, and `npm run test`;
3. Describe the change, verification, and impact in the PR.

## Support & Contact

If WenShu saves you time, you can buy me a coffee. **Support is entirely optional and does not affect any functionality.**

For collaboration, customization, deployment, or questions, add me on WeChat and mention “WenShu”.

| Alipay | WeChat Pay | WeChat (contact) |
| --- | --- | --- |
| <img src="docs/assets/donate/alipay.png" width="220" alt="Alipay tip QR code"> | <img src="docs/assets/donate/wechat-pay.png" width="220" alt="WeChat Pay tip QR code"> | <img src="docs/assets/wechat-contact.png" width="220" alt="Author WeChat QR code for collaboration"> |

## License

[MIT](LICENSE) © 2026 QI Yufan

If this project helps you, a star is appreciated.
