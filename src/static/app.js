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
                ${terms.map((term) => `<span>${escapeHtml(term)}</span>`).join("")}
            </div>
        </div>
    `;
}

function renderResult(entry) {
    const literal = entry.literal
        ? `<p><strong>Literal translation:</strong> ${escapeHtml(entry.literal)}</p>`
        : "";

    return `
        <article class="result-card">
            <div class="result-header">
                <div>
                    <p class="eyebrow">${escapeHtml(entry.category)}</p>
                    <h2>${escapeHtml(entry.term)}</h2>
                </div>
                <span class="source-badge">${escapeHtml(entry.source)}</span>
            </div>
            <p><strong>Natural English:</strong> ${escapeHtml(entry.english)}</p>
            ${literal}
            <p><strong>Plain-English explanation:</strong> ${escapeHtml(entry.explanation)}</p>
            <p><strong>Business/CRM context:</strong> ${escapeHtml(entry.business_context)}</p>
            <div class="example-block">
                <span class="field-label">Example</span>
                <p lang="fr">${escapeHtml(entry.example_fr)}</p>
                <p>${escapeHtml(entry.example_en)}</p>
            </div>
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
    document.getElementById("result").innerHTML = `
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
            const result = document.getElementById("result");
            result.innerHTML = data.ok ? renderResult(data.result) : renderNotFound(data.query || query);
            input.focus();
        })
        .catch(() => {
            document.getElementById("result").innerHTML = renderNotFound(query);
            input.focus();
        });
}

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("lookup-form");
    if (form) {
        form.addEventListener("submit", handleLookup);
    }
});
