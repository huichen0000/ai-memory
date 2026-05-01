document.addEventListener('DOMContentLoaded', function() {
    initTabs();
    loadMemories();
});

function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabId = button.getAttribute('data-tab');

            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));

            button.classList.add('active');
            document.getElementById('tab-' + tabId).classList.add('active');

            if (tabId === 'review') {
                loadReview();
            }
        });
    });

    document.getElementById('refresh-btn').addEventListener('click', loadMemories);
    document.getElementById('refresh-review-btn').addEventListener('click', loadReview);
}

async function loadMemories() {
    const container = document.getElementById('memories-container');
    container.innerHTML = '<p>Loading...</p>';

    try {
        const statusSelect = document.getElementById('filter-status');
        const selectedStatuses = Array.from(statusSelect.selectedOptions)
            .map(opt => opt.value)
            .join(',');

        const searchInput = document.getElementById('search-input');
        const query = searchInput.value.trim();

        const params = new URLSearchParams();
        if (selectedStatuses) params.append('status', selectedStatuses);
        if (query) params.append('q', query);
        params.append('limit', '50');

        const response = await fetch('/api/memories?' + params.toString());
        if (!response.ok) {
            throw new Error('Failed to fetch memories: ' + response.statusText);
        }

        const data = await response.json();
        renderMemories(data.memories);
    } catch (error) {
        container.innerHTML = '<p class="error">Error: ' + error.message + '</p>';
    }
}

function renderMemories(memories) {
    const container = document.getElementById('memories-container');

    if (!memories || memories.length === 0) {
        container.innerHTML = '<p>No memories found.</p>';
        return;
    }

    const html = memories.map(memory => `
        <div class="memory-card" data-id="${memory.id}">
            <div class="memory-header">
                <span class="memory-type">${escapeHtml(memory.type)}</span>
                <span class="memory-scope">${escapeHtml(memory.scope)}</span>
                <span class="memory-status status-${memory.status}">${escapeHtml(memory.status)}</span>
            </div>
            <div class="memory-summary">${escapeHtml(memory.summary)}</div>
            <div class="memory-meta">
                <span class="memory-confidence">Confidence: ${memory.confidence.toFixed(2)}</span>
                <span class="memory-risk">Risk: ${escapeHtml(memory.risk)}</span>
            </div>
            <div class="memory-uri">${escapeHtml(memory.uri)}</div>
            <div class="memory-dates">
                Created: ${formatDate(memory.created_at)} | Updated: ${formatDate(memory.updated_at)}
            </div>
            <div class="memory-actions">
                <button onclick="openEditor('${memory.id}', '${escapeHtml(memory.uri).replace(/'/g, "\\'")}', `${escapeHtml(memory.content).replace(/`/g, "\\`").replace(/\$/g, "\\$")}`)">Edit</button>
            </div>
        </div>
    `).join('');

    container.innerHTML = html;
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(isoString) {
    if (!isoString) return 'N/A';
    try {
        return new Date(isoString).toLocaleString();
    } catch {
        return isoString;
    }
}

function openEditor(id, uri, content) {
    document.getElementById('edit-id').value = id;
    document.getElementById('edit-uri').textContent = uri;
    document.getElementById('edit-content').value = content;
    document.getElementById('editor-modal').style.display = 'block';
}

function closeEditor() {
    document.getElementById('editor-modal').style.display = 'none';
}

async function saveMemory() {
    const id = document.getElementById('edit-id').value;
    const content = document.getElementById('edit-content').value;

    if (!content || !content.trim()) {
        alert('Content cannot be empty');
        return;
    }

    try {
        const response = await fetch('/api/memories/' + id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: content })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save');
        }

        closeEditor();
        loadMemories();
    } catch (error) {
        alert('Error saving memory: ' + error.message);
    }
}

async function loadReview() {
    const container = document.getElementById('review-list');
    container.innerHTML = '<p>Loading...</p>';

    try {
        const response = await fetch('/api/review');
        if (!response.ok) {
            throw new Error('Failed to fetch review items: ' + response.statusText);
        }

        const data = await response.json();
        renderReview(data.items);
    } catch (error) {
        container.innerHTML = '<p class="error">Error: ' + error.message + '</p>';
    }
}

function renderReview(items) {
    const container = document.getElementById('review-list');

    if (!items || items.length === 0) {
        container.innerHTML = '<p>No pending review items.</p>';
        return;
    }

    const html = items.map(item => `
        <div class="memory-card" data-id="${item.id}">
            <div class="memory-header">
                <span class="memory-type">${escapeHtml(item.candidate.type)}</span>
                <span class="memory-scope">${escapeHtml(item.candidate.scope)}</span>
                <span class="memory-confidence">Confidence: ${item.candidate.confidence.toFixed(2)}</span>
                <span class="memory-risk">Risk: ${escapeHtml(item.candidate.risk)}</span>
            </div>
            <div class="memory-summary">${escapeHtml(item.candidate.summary)}</div>
            <div class="memory-content-preview">${escapeHtml(truncate(item.candidate.content, 200))}</div>
            <div class="memory-uri">${escapeHtml(item.candidate.uri)}</div>
            <div class="review-reason"><strong>Reason:</strong> ${escapeHtml(item.reason)}</div>
            <div class="memory-dates">
                Created: ${formatDate(item.created_at)}
            </div>
            <div class="memory-actions">
                <button onclick="handleReview('${item.id}', 'approve')">Approve</button>
                <button onclick="handleReview('${item.id}', 'reject')">Reject</button>
            </div>
        </div>
    `).join('');

    container.innerHTML = html;
}

function truncate(text, maxLength) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

async function handleReview(id, action) {
    try {
        const response = await fetch('/api/review/' + id + '/' + action, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to ' + action);
        }

        loadReview();
    } catch (error) {
        alert('Error: ' + error.message);
    }
}
