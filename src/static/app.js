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

function renderVocabulary(vocabulary) {
    if (!vocabulary.length) {
        return "";
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

function setActiveMode(mode) {
    const lookupIsActive = mode === "lookup";
    document.getElementById("lookup-tab").classList.toggle("is-active", lookupIsActive);
    document.getElementById("lookup-tab").setAttribute("aria-selected", String(lookupIsActive));
    document.getElementById("translate-tab").classList.toggle("is-active", !lookupIsActive);
    document.getElementById("translate-tab").setAttribute("aria-selected", String(!lookupIsActive));
    document.getElementById("lookup-mode").hidden = !lookupIsActive;
    document.getElementById("translate-mode").hidden = lookupIsActive;
    document.getElementById("lookup-result").hidden = !lookupIsActive;
    document.getElementById("translate-result").hidden = lookupIsActive;
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
    });

    const translateForm = document.getElementById("translate-form");
    const translateInput = document.getElementById("translate-input");
    if (translateForm && translateInput) {
        translateForm.addEventListener("submit", handleTranslate);
        translateInput.addEventListener("input", () => {
            document.getElementById("character-count").textContent = `${translateInput.value.length.toLocaleString()} / 6,000`;
        });
    }

    document.getElementById("lookup-tab").addEventListener("click", () => setActiveMode("lookup"));
    document.getElementById("translate-tab").addEventListener("click", () => setActiveMode("translate"));
});
