function escapeHtml(value) {
    return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function renderRelatedTerms(terms) {
    if (!terms || terms.length === 0) {
        return "";
    }

    return `
        <div class="field-block">
            <span class="field-label">Related terms</span>
            <div class="related-list">
                ${terms.map((term) => `<button type="button" class="related-term" data-query="${escapeHtml(term)}">${escapeHtml(term)}</button>`).join("")}
            </div>
        </div>
    `;
}

function renderResult(entry) {
    const literal = entry.literal_translation
        ? `<p><strong>Literal translation:</strong> ${escapeHtml(entry.literal_translation)}</p>`
        : "";
    const examples = entry.examples.map((example) => `
        <div class="example-block">
            <span class="field-label">Example</span>
            <p lang="fr">${escapeHtml(example.french)}</p>
            <p>${escapeHtml(example.english)}</p>
        </div>
    `).join("");

    return `
        <article class="result-card">
            <div class="result-header">
                <div>
                    <p class="eyebrow">${escapeHtml(entry.category)}</p>
                    <h2>${escapeHtml(entry.term)}</h2>
                </div>
                <span class="source-badge">Source: ${escapeHtml(entry.source)}</span>
            </div>
            <p><strong>Natural English:</strong> ${escapeHtml(entry.english)}</p>
            ${literal}
            <p><strong>Plain-English explanation:</strong> ${escapeHtml(entry.explanation)}</p>
            <p><strong>Business/CRM context:</strong> ${escapeHtml(entry.business_context)}</p>
            ${examples}
            ${renderRelatedTerms(entry.related_terms)}
            <div class="save-actions">
                <button type="button" class="save-term-button save-glossary-term" data-term="${escapeHtml(entry.term)}">Save term</button>
                <span class="save-feedback" aria-live="polite"></span>
            </div>
        </article>
    `;
}

function renderNotFound(query) {
    return `
        <article class="empty-state">
            <h2>Not found</h2>
            <p>No glossary entry exists for "${escapeHtml(query)}". Try another French workplace or CRM term.</p>
        </article>
    `;
}

function setLoading() {
    document.getElementById("lookup-result").innerHTML = `
        <article class="empty-state">
            <p>Searching...</p>
        </article>
    `;
}

function handleLookup(event) {
    event.preventDefault();

    const input = document.getElementById("lookup-input");
    const query = input.value.trim();
    if (!query) {
        input.focus();
        return;
    }

    setLoading();

    fetch("/api/lookup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
    })
        .then((response) => response.json().then((data) => ({ status: response.status, data })))
        .then(({ data }) => {
            const result = document.getElementById("lookup-result");
            result.innerHTML = data.ok ? renderResult(data.result) : renderNotFound(data.query || query);
            input.focus();
        })
        .catch(() => {
            document.getElementById("lookup-result").innerHTML = renderNotFound(query);
            input.focus();
        });
}

function performLookup(query) {
    const input = document.getElementById("lookup-input");
    input.value = query;
    document.getElementById("lookup-form").requestSubmit();
}

function renderTranslateError(message) {
    return `<article class="empty-state"><h2>Unable to translate</h2><p>${escapeHtml(message)}</p></article>`;
}

function renderVocabulary(vocabulary, emptyMessage = "") {
    if (!vocabulary.length) {
        return emptyMessage
            ? `<section class="translate-section"><h3>Important Vocabulary</h3><p class="section-empty">${escapeHtml(emptyMessage)}</p></section>`
            : "";
    }

    return `
        <section class="translate-section">
            <h3>Important Vocabulary</h3>
            <div class="vocabulary-list">
                ${vocabulary.map((item) => `
                    <article class="vocabulary-item">
                        <h4>${escapeHtml(item.french)}</h4>
                        <p><strong>${escapeHtml(item.english)}</strong></p>
                        <p>${escapeHtml(item.explanation)}</p>
                        <div class="save-actions">
                            <button type="button" class="save-term-button save-ai-term" data-french="${escapeHtml(item.french)}" data-english="${escapeHtml(item.english)}" data-explanation="${escapeHtml(item.explanation)}">Save term</button>
                            <span class="save-feedback" aria-live="polite"></span>
                        </div>
                    </article>
                `).join("")}
            </div>
        </section>
    `;
}

function renderTranslateResult(result) {
    const businessContext = result.business_crm_context
        ? `<section class="translate-section"><h3>Business / CRM Context</h3><p>${escapeHtml(result.business_crm_context)}</p></section>`
        : "";
    const developerInterpretation = result.developer_interpretation
        ? `<section class="translate-section"><h3>Developer Interpretation</h3><p>${escapeHtml(result.developer_interpretation)}</p></section>`
        : "";

    return `
        <article class="result-card translate-result-card">
            <section class="translate-section">
                <h2>Natural English Translation</h2>
                <p>${escapeHtml(result.natural_english_translation)}</p>
            </section>
            <section class="translate-section">
                <h3>Plain-English Meaning</h3>
                <p>${escapeHtml(result.plain_english_meaning)}</p>
            </section>
            ${businessContext}
            ${renderVocabulary(result.important_vocabulary)}
            ${developerInterpretation}
        </article>
    `;
}

function handleTranslate(event) {
    event.preventDefault();

    const input = document.getElementById("translate-input");
    const text = input.value.trim();
    const result = document.getElementById("translate-result");
    if (!text) {
        input.focus();
        return;
    }

    result.innerHTML = `<article class="empty-state"><p>Translating and explaining locally with Ollama...</p></article>`;

    fetch("/api/translate-explain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
    })
        .then((response) => response.json().then((data) => ({ status: response.status, data })))
        .then(({ data }) => {
            result.innerHTML = data.ok ? renderTranslateResult(data.result) : renderTranslateError(data.error);
        })
        .catch(() => {
            result.innerHTML = renderTranslateError("The local service could not be reached. Check that Ollama is running and try again.");
        });
}

function renderCopyButton(content, label) {
    return `<button type="button" class="copy-button" data-copy-content="${escapeHtml(content)}">${escapeHtml(label)}</button>`;
}

function renderDeveloperList(title, items, kind) {
    const content = items.map((item) => `- ${item}`).join("\n");
    const emptyMessage = kind === "explicit"
        ? "No explicit requirements were identified in the source."
        : kind === "interpretation"
            ? "No implementation interpretations were identified."
            : "No source-specific questions were identified.";
    return `
        <section class="developer-section developer-${escapeHtml(kind)}">
            <div class="section-heading">
                <h3>${escapeHtml(title)}</h3>
                ${items.length ? renderCopyButton(content, "Copy") : ""}
            </div>
            ${items.length
                ? `<ul class="developer-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
                : `<p class="section-empty">${emptyMessage}</p>`}
        </section>
    `;
}

function buildDeveloperCopyText(result) {
    return [
        `Natural English Translation\n${result.translation}`,
        `Explicit Requirements\n${result.explicit_requirements.map((item) => `- ${item}`).join("\n")}`,
        `Implementation Notes (interpretations, not confirmed requirements)\n${result.implementation_notes.map((item) => `- ${item}`).join("\n")}`,
        `Important Vocabulary\n${result.important_vocabulary.map((item) => `- ${item.french}: ${item.english}`).join("\n")}`,
        `Ambiguities / Questions\n${result.ambiguities.map((item) => `- ${item}`).join("\n")}`,
    ].join("\n\n");
}

function renderDeveloperResult(result) {
    const vocabulary = renderVocabulary(result.important_vocabulary, "No important vocabulary was identified.");
    return `
        <article class="result-card developer-result-card">
            <section class="developer-section developer-translation">
                <div class="section-heading">
                    <h2>Natural English Translation</h2>
                    ${renderCopyButton(result.translation, "Copy")}
                </div>
                <p>${escapeHtml(result.translation)}</p>
            </section>
            ${renderDeveloperList("Explicit Requirements (Source-stated)", result.explicit_requirements, "explicit")}
            ${renderDeveloperList("Implementation Notes (Interpretations)", result.implementation_notes, "interpretation")}
            ${vocabulary}
            ${renderDeveloperList("Ambiguities / Questions", result.ambiguities, "ambiguity")}
            <div class="developer-full-copy">
                ${renderCopyButton(buildDeveloperCopyText(result), "Copy full result")}
            </div>
        </article>
    `;
}

function handleDeveloperMode(event) {
    event.preventDefault();

    const input = document.getElementById("developer-input");
    const text = input.value.trim();
    const result = document.getElementById("developer-result");
    if (!text) {
        input.focus();
        return;
    }

    result.innerHTML = `<article class="empty-state"><p>Interpreting locally with Ollama...</p></article>`;
    fetch("/api/developer-mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
    })
        .then((response) => response.json().then((data) => ({ status: response.status, data })))
        .then(({ data }) => {
            result.innerHTML = data.ok ? renderDeveloperResult(data.result) : renderTranslateError(data.error);
        })
        .catch(() => {
            result.innerHTML = renderTranslateError("The local service could not be reached. Check that Ollama is running and try again.");
        });
}

function copyText(button) {
    const content = button.dataset.copyContent;
    const showCopied = () => {
        const label = button.textContent;
        button.textContent = "Copied";
        window.setTimeout(() => {
            button.textContent = label;
        }, 1200);
    };
    const fallbackCopy = () => {
        const temporaryInput = document.createElement("textarea");
        temporaryInput.value = content;
        temporaryInput.setAttribute("readonly", "");
        temporaryInput.className = "sr-only";
        document.body.appendChild(temporaryInput);
        temporaryInput.select();
        const copied = document.execCommand("copy");
        temporaryInput.remove();
        if (copied) {
            showCopied();
        }
    };

    if (navigator.clipboard) {
        navigator.clipboard.writeText(content).then(showCopied).catch(fallbackCopy);
    } else {
        fallbackCopy();
    }
}

function setActiveMode(mode) {
    const lookupIsActive = mode === "lookup";
    const translateIsActive = mode === "translate";
    const developerIsActive = mode === "developer";
    const savedIsActive = mode === "saved";
    document.getElementById("lookup-tab").classList.toggle("is-active", lookupIsActive);
    document.getElementById("lookup-tab").setAttribute("aria-selected", String(lookupIsActive));
    document.getElementById("translate-tab").classList.toggle("is-active", translateIsActive);
    document.getElementById("translate-tab").setAttribute("aria-selected", String(translateIsActive));
    document.getElementById("developer-tab").classList.toggle("is-active", developerIsActive);
    document.getElementById("developer-tab").setAttribute("aria-selected", String(developerIsActive));
    document.getElementById("saved-tab").classList.toggle("is-active", savedIsActive);
    document.getElementById("saved-tab").setAttribute("aria-selected", String(savedIsActive));
    document.getElementById("lookup-mode").hidden = !lookupIsActive;
    document.getElementById("translate-mode").hidden = !translateIsActive;
    document.getElementById("developer-mode").hidden = !developerIsActive;
    document.getElementById("saved-mode").hidden = !savedIsActive;
    document.getElementById("lookup-result").hidden = !lookupIsActive;
    document.getElementById("translate-result").hidden = !translateIsActive;
    document.getElementById("developer-result").hidden = !developerIsActive;
    document.getElementById("saved-result").hidden = !savedIsActive;
    if (savedIsActive) {
        loadSavedTerms();
    }
}

function setSaveFeedback(button, message, saved) {
    const feedback = button.parentElement.querySelector(".save-feedback");
    button.disabled = saved;
    if (saved) {
        button.textContent = message;
    }
    feedback.textContent = saved ? "" : message;
}

function saveTerm(button, payload) {
    button.disabled = true;
    fetch("/api/saved-terms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    })
        .then((response) => response.json().then((data) => ({ status: response.status, data })))
        .then(({ data }) => {
            if (data.ok) {
                setSaveFeedback(button, data.message, true);
            } else {
                button.disabled = false;
                setSaveFeedback(button, data.error || "Unable to save term.", false);
            }
        })
        .catch(() => {
            button.disabled = false;
            setSaveFeedback(button, "Unable to save term.", false);
        });
}

function formatSavedDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "Saved locally" : date.toLocaleString();
}

function renderSavedTerms(terms, total) {
    document.getElementById("saved-total").textContent = `${total} saved term${total === 1 ? "" : "s"}`;
    if (!terms.length) {
        return `<article class="empty-state"><h2>No saved terms</h2><p>Save a term from Quick Lookup or Translate &amp; Explain to find it here.</p></article>`;
    }

    return `
        <div class="saved-list">
            ${terms.map((term) => `
                <article class="saved-term-card">
                    <div class="saved-term-header">
                        <div>
                            <h3>${escapeHtml(term.french)}</h3>
                            <p><strong>${escapeHtml(term.english)}</strong></p>
                        </div>
                        <span class="source-badge">Source: ${escapeHtml(term.source)}</span>
                    </div>
                    ${term.category ? `<p><strong>Category:</strong> ${escapeHtml(term.category)}</p>` : ""}
                    <p class="saved-date">Saved ${escapeHtml(formatSavedDate(term.saved_at))}</p>
                    <button type="button" class="delete-term-button" data-id="${term.id}" data-term="${escapeHtml(term.french)}">Delete</button>
                </article>
            `).join("")}
        </div>
    `;
}

function loadSavedTerms(event) {
    if (event) {
        event.preventDefault();
    }
    const query = document.getElementById("saved-search").value.trim();
    const source = document.getElementById("saved-source-filter").value;
    const result = document.getElementById("saved-result");
    result.innerHTML = `<article class="empty-state"><p>Loading saved terms...</p></article>`;
    const parameters = new URLSearchParams();
    if (query) {
        parameters.set("q", query);
    }
    if (source) {
        parameters.set("source", source);
    }

    fetch(`/api/saved-terms?${parameters.toString()}`)
        .then((response) => response.json().then((data) => ({ status: response.status, data })))
        .then(({ data }) => {
            result.innerHTML = data.ok ? renderSavedTerms(data.terms, data.total) : renderTranslateError(data.error || "Unable to load saved terms.");
        })
        .catch(() => {
            result.innerHTML = renderTranslateError("Unable to load saved terms.");
        });
}

function deleteSavedTerm(button) {
    const term = button.dataset.term;
    if (!window.confirm(`Delete "${term}" from Saved Terms?`)) {
        return;
    }
    button.disabled = true;
    fetch(`/api/saved-terms/${button.dataset.id}`, { method: "DELETE" })
        .then((response) => response.json().then((data) => ({ status: response.status, data })))
        .then(({ data }) => {
            if (data.ok) {
                loadSavedTerms();
            } else {
                button.disabled = false;
            }
        })
        .catch(() => {
            button.disabled = false;
        });
}

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("lookup-form");
    if (form) {
        form.addEventListener("submit", handleLookup);
    }

    document.getElementById("lookup-result").addEventListener("click", (event) => {
        const relatedTerm = event.target.closest(".related-term");
        if (relatedTerm) {
            performLookup(relatedTerm.dataset.query);
        }
        const glossaryButton = event.target.closest(".save-glossary-term");
        if (glossaryButton) {
            saveTerm(glossaryButton, { kind: "glossary", term: glossaryButton.dataset.term });
        }
    });

    document.getElementById("translate-result").addEventListener("click", (event) => {
        const aiButton = event.target.closest(".save-ai-term");
        if (aiButton) {
            saveTerm(aiButton, {
                kind: "ai_vocabulary",
                french: aiButton.dataset.french,
                english: aiButton.dataset.english,
                explanation: aiButton.dataset.explanation,
            });
        }
    });

    const translateForm = document.getElementById("translate-form");
    const translateInput = document.getElementById("translate-input");
    if (translateForm && translateInput) {
        translateForm.addEventListener("submit", handleTranslate);
        translateInput.addEventListener("input", () => {
            document.getElementById("character-count").textContent = `${translateInput.value.length.toLocaleString()} / 6,000`;
        });
    }

    const developerForm = document.getElementById("developer-form");
    const developerInput = document.getElementById("developer-input");
    if (developerForm && developerInput) {
        developerForm.addEventListener("submit", handleDeveloperMode);
        developerInput.addEventListener("input", () => {
            document.getElementById("developer-character-count").textContent = `${developerInput.value.length.toLocaleString()} / 6,000`;
        });
    }

    document.getElementById("developer-result").addEventListener("click", (event) => {
        const copyButton = event.target.closest(".copy-button");
        if (copyButton) {
            copyText(copyButton);
        }
        const aiButton = event.target.closest(".save-ai-term");
        if (aiButton) {
            saveTerm(aiButton, {
                kind: "ai_vocabulary",
                french: aiButton.dataset.french,
                english: aiButton.dataset.english,
                explanation: aiButton.dataset.explanation,
            });
        }
    });

    document.getElementById("lookup-tab").addEventListener("click", () => setActiveMode("lookup"));
    document.getElementById("translate-tab").addEventListener("click", () => setActiveMode("translate"));
    document.getElementById("developer-tab").addEventListener("click", () => setActiveMode("developer"));
    document.getElementById("saved-tab").addEventListener("click", () => setActiveMode("saved"));
    document.getElementById("saved-search-form").addEventListener("submit", loadSavedTerms);
    document.getElementById("saved-source-filter").addEventListener("change", loadSavedTerms);
    document.getElementById("saved-result").addEventListener("click", (event) => {
        const deleteButton = event.target.closest(".delete-term-button");
        if (deleteButton) {
            deleteSavedTerm(deleteButton);
        }
    });
});
