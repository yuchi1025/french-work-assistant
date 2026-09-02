# French Work Assistant

French Work Assistant is a local web app for English-speaking developers who work with French-speaking teams. It helps turn French workplace, CRM, product, and software text into practical English context without sending that text to remote AI services.

Version: `v1.0.0`

## Why I Built This

Literal translation is often not enough for workplace language. A French CRM status, UI label, requirement, or issue description may imply business context or implementation concerns that are easy to miss. This project keeps that help local and makes the difference between source text, interpretation, and open questions visible.

## Features

- **Quick Lookup**: Search French or English workplace and CRM terms. Glossary matches always win; a concise, clearly labeled local Ollama fallback runs only when no glossary entry matches. Results can be saved locally.
- **Translate & Explain**: Translate French text naturally and explain its plain-English and workplace context with local Ollama.
- **Developer Mode**: Interpret French requirements and issue text as translation, source-stated requirements, implementation interpretations, vocabulary, and ambiguities. Interpretation is clearly labeled as non-authoritative.
- **Saved Terms**: Keep individual terms locally, then search, filter, and delete them.
- **Custom Glossary**: Add organization-specific terminology locally without committing it to this public repository.

## Local-First Privacy

- Ollama runs locally. Translate & Explain, Developer Mode, and Quick Lookup fallback accept only loopback Ollama URLs such as `127.0.0.1` and `localhost`.
- The app does not call OpenAI, Google, DeepL, analytics tools, or other remote AI APIs.
- Submitted AI text and complete AI results are not written to files or SQLite. Translate & Explain has a bounded in-memory cache for the running process only.
- Saved Terms uses local SQLite at `data/saved_terms.db` and saves only terms selected explicitly by the user.
- Organization-specific custom terms belong in the gitignored `data/custom_glossary.json`.

## Tech Stack

- Python and Flask
- HTML, CSS, and Vanilla JavaScript
- Ollama and `gemma3` for optional local AI processing
- SQLite for private Saved Terms history
- pytest

## Getting Started

```bash
git clone https://github.com/yuchi1025/french-work-assistant.git
cd french-work-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Glossary-backed Quick Lookup and Saved Terms work without Ollama. Unknown Quick Lookup terms and the other AI modes use local Ollama; install the default model with:

```bash
ollama pull gemma3
ollama serve
```

Run the app:

```bash
python3 src/app.py
```

Open `http://127.0.0.1:5000`.

## Configuration

The defaults are in [.env.example](.env.example). Environment variables are optional:

- `OLLAMA_URL`: local Ollama chat endpoint. Default: `http://127.0.0.1:11434/api/chat`
- `OLLAMA_MODEL`: installed local model. Default: `gemma3`
- `OLLAMA_KEEP_ALIVE`: model keep-alive value. Default: `15m`
- `OLLAMA_TIMEOUT`: request timeout in seconds. Default: `45`

The project does not load `.env` itself. Export variables in your shell or use a process manager that loads a local `.env`. `.env` is gitignored.

## Custom Glossary

Static glossary data is public reference terminology:

- `data/workplace_glossary.json`: general workplace French
- `data/crm_glossary.json`: generic CRM and sales French

Private terminology is optional and local:

```bash
cp data/custom_glossary.example.json data/custom_glossary.json
```

`data/custom_glossary.json` is gitignored and never required for startup. When the same term exists in multiple layers, lookup precedence is **Custom > CRM > Workplace**. Public glossaries are validated at startup; invalid custom data returns a generic error that does not reveal private content.

## Testing

```bash
python3 -m pytest
```

Tests mock Ollama, use temporary SQLite databases, and use only generic or fictional examples. They do not depend on a local custom glossary, real saved database, or live Ollama server.

## Limitations

- A local Ollama model can return an error, timeout, or invalid JSON. The app presents a safe retryable error in those cases.
- AI translations and explanations are assistance, not authoritative business decisions.
- In Developer Mode, **Explicit Requirements** are source-stated; **Implementation Notes** are suggestions. Confirm ambiguous requirements with the original author or product owner before implementing.
- This project intentionally has no accounts, cloud sync, remote AI APIs, deployment configuration, or automatic code generation.

## Privacy

Do not commit customer data, internal URLs, credentials, copied client messages, confidential requirements, `.env`, `data/custom_glossary.json`, or `data/saved_terms.db`. The latter three are gitignored. Deleting a Saved Term changes only local SQLite history, never a public or custom glossary file.

## Project Status

The feature set is complete and the project is prepared for its first polished `v1.0.0` release. Review the current changes and test suite before creating a tag or GitHub release.
