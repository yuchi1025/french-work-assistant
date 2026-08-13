# French Work Assistant

French Work Assistant is a local web app for English-speaking developers who work with French-speaking teams and need help understanding French workplace, CRM, and software-development terms.

Current version: `v0.1`

## What It Does

The app provides three local-first modes.

### Quick Lookup

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

Related terms are buttons: selecting one runs another Quick Lookup search. Built-in terminology is generic and public; it does not encode an organization's private CRM rules or workflow behavior.

### Translate & Explain

Paste French workplace, CRM, product, or software-development text and receive:

- Natural English Translation
- Plain-English Meaning
- Business / CRM Context when the source text supports one
- Important Vocabulary with French, English, and a short explanation
- Developer Interpretation when the source text describes software behavior, workflows, statuses, permissions, UI behavior, or implementation requirements

For example, a generic input such as `Lorsqu'un prospect est marqué comme hors cible, il ne doit plus apparaître dans la liste des prospects actifs.` can be translated and interpreted as a likely product behavior. The app does not invent business context or developer requirements where none are present.

Translate & Explain accepts up to `6,000` characters per request, which is intended for a workplace paragraph or a compact requirement. It does not save submitted text to files, databases, or history. Successful results may remain in a bounded in-memory cache for the lifetime of the running process only; restarting the app clears it.

### Saved Terms

Save individual terms you want to keep from Quick Lookup or the Important Vocabulary section of Translate & Explain. Saving is always explicit: the app never saves a Quick Lookup result, AI vocabulary item, translated input, or AI response automatically.

Saved Terms provides a private local list with a total count, French/English search, source filtering, newest-first ordering, and deletion. Deleting a saved term removes only that personal-history row. It never changes a public glossary file or a local custom glossary.

## Local-First Privacy

Translate & Explain sends text only to a local Ollama server at `OLLAMA_URL`, which defaults to `http://127.0.0.1:11434/api/chat`. The application accepts only loopback Ollama URLs such as `localhost`, `127.0.0.1`, or `::1`; a remote host is rejected. It does not call OpenAI, Google, DeepL, external translation services, analytics providers, or remote AI APIs.

The application does not persist submitted text by default and does not deliberately log submitted text. Still, use a locally managed Ollama installation and follow your organization's data-handling policy before pasting sensitive material. Never commit private workplace text, customer data, internal URLs, credentials, or confidential requirements to this public repository.

Saved Terms is stored locally in `data/saved_terms.db`, a gitignored SQLite database. It stores only the individual terms you explicitly save: French, English, optional literal translation, category, explanation, business context, source, and a timestamp. It does not store full Translate & Explain input or full AI responses. The database has a unique normalized French-term key, so saving the same term again reports `Already saved` instead of creating a duplicate.

## Public And Private Data

This repository is designed to be public.

Quick Lookup has three glossary layers:

- `data/workplace_glossary.json`: public, general French workplace vocabulary such as scheduling and early requirements work.
- `data/crm_glossary.json`: public, generic CRM and sales vocabulary such as prospects, follow-ups, qualification, call outcomes, and data quality.
- `data/custom_glossary.json`: optional local terminology for one organization. It is never required for startup and is not committed.

When the same normalized French term appears in more than one layer, Quick Lookup chooses it deterministically in this order:

1. Custom
2. CRM
3. Workplace

Quick Lookup searches French and English terms case-insensitively. It normalizes common Unicode variants and French accents, ranks exact matches before simple partial matches, and supports abbreviations such as `RDV`.

`data/custom_glossary.json` is gitignored so local organization-specific terms cannot be added to a public commit by default. Create it from the safe fictional template:

```bash
cp data/custom_glossary.example.json data/custom_glossary.json
```

Do not commit real customer data, private CRM notes, credentials, internal URLs, copied client communications, or company-specific confidential information. The public example intentionally uses fictional generic content and no real organization name.

### Glossary Schema And Validation

New entries should use this schema:

```json
{
  "term": "priority lead",
  "english": "priority lead",
  "literal_translation": "priority lead",
  "category": "Custom workflow",
  "explanation": "A concise explanation.",
  "business_context": "The organization defines its exact workflow meaning.",
  "examples": [
    {
      "french": "Ce priority lead doit être traité rapidement.",
      "english": "This priority lead should be handled promptly."
    }
  ],
  "related_terms": ["prospect", "relance"]
}
```

For compatibility, the earlier `literal`, `example_fr`, and `example_en` fields are still accepted and normalized internally to `literal_translation` and `examples`.

Public glossary files are validated during application startup. Invalid JSON, a non-array top level, missing or empty required strings, wrong types, malformed examples or related terms, and duplicate normalized terms within one file fail clearly. An invalid optional custom glossary also stops startup, but its error intentionally omits the file's private terms and contents.

Static glossary data is public reference terminology. `data/saved_terms.db` is separate private personal history and must not be committed.

## Technology

- Python
- Flask
- HTML
- CSS
- Vanilla JavaScript
- Ollama for optional local AI processing
- SQLite for private Saved Terms history
- pytest

There is no authentication, cloud sync, remote database, deployment configuration, or remote AI integration.

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
│   ├── custom_glossary.example.json
│   └── saved_terms.db (local, gitignored, created when needed)
└── tests/
    ├── conftest.py
    ├── test_glossary.py
    ├── test_routes.py
    └── test_translate_explain.py
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

## Local Ollama Setup

Quick Lookup works without Ollama. Translate & Explain requires a local Ollama installation and the default `gemma3` model:

```bash
ollama pull gemma3
ollama serve
```

Ollama normally listens on `http://127.0.0.1:11434`. The app reads these optional environment variables at startup:

- `OLLAMA_URL`: local Ollama chat endpoint. Default: `http://127.0.0.1:11434/api/chat`
- `OLLAMA_MODEL`: installed local model. Default: `gemma3`
- `OLLAMA_KEEP_ALIVE`: how long Ollama keeps the model loaded. Default: `15m`
- `OLLAMA_TIMEOUT`: request timeout in seconds. Default: `45`

Copy `.env.example` to a local `.env` only if your shell or process manager loads environment files. `.env` remains gitignored. Flask itself does not automatically read `.env` in this project, so exporting variables in your shell also works:

```bash
export OLLAMA_MODEL=gemma3
export OLLAMA_TIMEOUT=45
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

The tests cover public/custom glossary loading, strict validation, duplicate detection, source metadata, Custom > CRM > Workplace precedence, French and English lookup, Unicode/accent normalization, abbreviations, related terms, and Quick Lookup routes.

They also use temporary SQLite files to cover Saved Terms initialization, explicit glossary/AI saves, duplicate prevention, listing, search, filters, ordering, deletion, and invalid requests. The AI tests mock the local Ollama HTTP call to cover successful structured results, invalid input, request length limits, malformed model JSON, invalid AI schemas, unavailable Ollama, and timeouts. No test needs a real Ollama server, real saved-terms database, or non-public workplace data.

## Limitations

- Translate & Explain depends on a locally installed Ollama model and may return an error while Ollama is stopped, still loading, or produces invalid JSON.
- Model explanations are assistance, not an authoritative source of business requirements. Check ambiguous wording with the French-speaking author or product owner.
- This version intentionally has no cloud sync, custom translation memory, remote AI APIs, authentication, or deployment configuration.
