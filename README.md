# French Work Assistant

French Work Assistant is a local web app for English-speaking developers who work with French-speaking teams and need help understanding French workplace, CRM, and software-development terms.

Current version: `v0`

## What It Does

The v0 app provides one mode: Quick Lookup.

1. Enter a French word or short phrase.
2. Click Search.
3. If the term exists in the local glossary, the app shows a structured explanation.
4. If it is not found, the app shows a clear not-found result.

Each glossary result includes:

- French term
- Natural English translation
- Literal translation, when useful
- Category
- Plain-English explanation
- Business/CRM context
- One example French sentence
- English translation of the example
- Related terms

The built-in glossary uses only generic, public workplace and CRM terminology.

## Public And Private Data

This repository is designed to be public.

Public glossary files are committed:

- `data/workplace_glossary.json`
- `data/crm_glossary.json`
- `data/custom_glossary.example.json`

Private local glossary data is optional and must stay local:

- `data/custom_glossary.json`

`data/custom_glossary.json` is gitignored and is not required for the app to run. To add private terms on your own machine, copy the example file to `data/custom_glossary.json` and edit that local file. Do not commit real customer data, private CRM notes, credentials, internal URLs, copied client communications, or company-specific confidential information.

## Technology

- Python
- Flask
- HTML
- CSS
- Vanilla JavaScript
- pytest

No AI, authentication, database, or deployment configuration is included in v0.

## Project Structure

```text
french-work-assistant/
├── README.md
├── LICENSE
├── requirements.txt
├── .gitignore
├── .env.example
├── src/
│   ├── app.py
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── style.css
│       └── app.js
├── data/
│   ├── workplace_glossary.json
│   ├── crm_glossary.json
│   └── custom_glossary.example.json
└── tests/
    ├── conftest.py
    ├── test_glossary.py
    └── test_routes.py
```

## Installation

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
python3 src/app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Testing

Run the test suite:

```bash
python3 -m pytest
```

The tests cover glossary loading, exact French lookup, case-insensitive lookup, English lookup, unknown terms, missing custom glossary behavior, temporary custom glossary loading, and the main Flask route.
