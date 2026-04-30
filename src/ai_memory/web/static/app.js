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
        });
    });

    document.getElementById('refresh-btn').addEventListener('click', loadMemories);
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
