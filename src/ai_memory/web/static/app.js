let currentUser = null;

document.addEventListener('DOMContentLoaded', function() {
    initTabs();
    checkAuth();
});

function getToken() {
    return localStorage.getItem('token');
}

function setToken(token) {
    localStorage.setItem('token', token);
}

function clearToken() {
    localStorage.removeItem('token');
}

function authHeaders() {
    const token = getToken();
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = 'Bearer ' + token;
    return headers;
}

async function checkAuth() {
    const token = getToken();
    if (!token) {
        showLogin();
        return;
    }
    try {
        const resp = await fetch('/api/auth/me', { headers: { 'Authorization': 'Bearer ' + token } });
        if (!resp.ok) {
            clearToken();
            showLogin();
            return;
        }
        currentUser = await resp.json();
        showLoggedIn();
        loadMemories();
    } catch (e) {
        clearToken();
        showLogin();
    }
}

function showLogin() {
    document.getElementById('login-bar').style.display = 'block';
    document.getElementById('user-bar').style.display = 'none';
    document.getElementById('tab-btn-users').style.display = 'none';
}

function showLoggedIn() {
    document.getElementById('login-bar').style.display = 'none';
    document.getElementById('user-bar').style.display = 'block';
    document.getElementById('user-info').textContent = currentUser.username + ' (' + currentUser.role + ')';
    if (currentUser.role === 'admin') {
        document.getElementById('tab-btn-users').style.display = '';
    } else {
        document.getElementById('tab-btn-users').style.display = 'none';
    }
}

async function login() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error');
    errorEl.textContent = '';

    if (!username || !password) {
        errorEl.textContent = 'Username and password required';
        return;
    }

    try {
        const resp = await fetch('/api/auth/login?username=' + encodeURIComponent(username) + '&password=' + encodeURIComponent(password), { method: 'POST' });
        if (!resp.ok) {
            const data = await resp.json();
            errorEl.textContent = data.detail || 'Login failed';
            return;
        }
        const data = await resp.json();
        setToken(data.token);
        currentUser = data.user;
        showLoggedIn();
        loadMemories();
    } catch (e) {
        errorEl.textContent = 'Network error';
    }
}

function logout() {
    clearToken();
    currentUser = null;
    showLogin();
}

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
            if (tabId === 'stats') {
                loadStats();
            }
            if (tabId === 'sources') {
                loadSources();
            }
            if (tabId === 'users') {
                loadUsers();
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

        const response = await fetch('/api/memories?' + params.toString(), { headers: authHeaders() });
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

    const html = memories.map(memory => {
        const safeUri = escapeHtml(memory.uri).replace(/'/g, "&#39;");
        const safeContent = escapeHtml(memory.content).replace(/`/g, "&#96;").replace(/\$/g, "&#36;");
        return `
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
                <button onclick="openEditor('${memory.id}', '${safeUri}', '${safeContent}')">Edit</button>
            </div>
        </div>`;
    }).join('');

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
    } catch (e) {
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
            headers: authHeaders(),
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
        const response = await fetch('/api/review', { headers: authHeaders() });
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
            headers: authHeaders()
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

async function loadStats() {
    try {
        const response = await fetch('/api/stats', { headers: authHeaders() });
        if (!response.ok) {
            throw new Error('Failed to fetch stats: ' + response.statusText);
        }
        const data = await response.json();
        renderStats(data);
    } catch (error) {
        document.getElementById('stat-total').textContent = 'Error';
    }
}

function renderStats(data) {
    document.getElementById('stat-total').textContent = data.total;
    renderBarChart(data.by_status, document.getElementById('chart-status'));
    renderBarChart(data.by_type, document.getElementById('chart-type'));
    renderBarChart(data.by_scope, document.getElementById('chart-scope'));
}

function renderBarChart(data, container) {
    if (!data || Object.keys(data).length === 0) {
        container.innerHTML = '<p>No data</p>';
        return;
    }

    const total = Object.values(data).reduce((a, b) => a + b, 0);
    const html = Object.entries(data).map(([label, count]) => {
        const pct = total > 0 ? (count / total * 100).toFixed(1) : 0;
        return `
        <div class="bar-row">
            <span class="bar-label">${escapeHtml(label)}</span>
            <div class="bar-container">
                <div class="bar" style="width:${pct}%"></div>
            </div>
            <span class="bar-value">${count}</span>
        </div>`;
    }).join('');

    container.innerHTML = html;
}

async function loadSources() {
    const container = document.getElementById('sources-list');
    container.innerHTML = '<p>Loading...</p>';

    try {
        const response = await fetch('/api/sources', { headers: authHeaders() });
        if (!response.ok) {
            throw new Error('Failed to fetch sources: ' + response.statusText);
        }

        const data = await response.json();
        renderSources(data.sources);
    } catch (error) {
        container.innerHTML = '<p class="error">Error: ' + error.message + '</p>';
    }
}

function renderSources(sources) {
    const container = document.getElementById('sources-list');
    const previewContainer = document.getElementById('source-preview-container');

    previewContainer.style.display = 'none';

    if (!sources || sources.length === 0) {
        container.innerHTML = '<p>No source archives found.</p>';
        return;
    }

    const html = '<table class="sources-table"><thead><tr><th>Client</th><th>Name</th><th>Size</th><th>Modified</th></tr></thead><tbody>' +
        sources.map(s => {
            const safePath = escapeHtml(s.path).replace(/'/g, "&#39;");
            return `
        <tr class="source-row" onclick="previewSource('${safePath}')">
            <td>${escapeHtml(s.client)}</td>
            <td>${escapeHtml(s.name)}</td>
            <td>${formatSize(s.size)}</td>
            <td>${formatDate(s.modified)}</td>
        </tr>`;
        }).join('') +
        '</tbody></table>';

    container.innerHTML = html;
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

async function previewSource(path) {
    const previewContainer = document.getElementById('source-preview-container');
    const previewContent = document.getElementById('source-preview');

    previewContainer.style.display = 'block';
    previewContent.textContent = 'Loading...';

    try {
        const encodedPath = encodeURIComponent(path);
        const response = await fetch('/api/sources/' + encodedPath, { headers: authHeaders() });

        if (!response.ok) {
            throw new Error('Failed to fetch source: ' + response.statusText);
        }

        const data = await response.json();
        previewContent.textContent = data.content;
    } catch (error) {
        previewContent.textContent = 'Error: ' + error.message;
    }
}

async function loadUsers() {
    const container = document.getElementById('users-list');
    container.innerHTML = '<p>Loading...</p>';

    try {
        const response = await fetch('/api/admin/users', { headers: authHeaders() });
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || 'Failed to fetch users');
        }

        const data = await response.json();
        renderUsers(data.users);
    } catch (error) {
        container.innerHTML = '<p class="error">Error: ' + error.message + '</p>';
    }
}

function renderUsers(users) {
    const container = document.getElementById('users-list');

    if (!users || users.length === 0) {
        container.innerHTML = '<p>No users found.</p>';
        return;
    }

    const html = '<table class="sources-table"><thead><tr><th>Username</th><th>Role</th><th>API Key</th><th>Actions</th></tr></thead><tbody>' +
        users.map(u => `
        <tr>
            <td>${escapeHtml(u.username)}</td>
            <td><span class="memory-status status-${u.role === 'admin' ? 'approved' : u.role === 'write' ? 'proposed' : 'pending'}">${escapeHtml(u.role)}</span></td>
            <td style="font-family:monospace; font-size:13px;">${escapeHtml(u.api_key)}</td>
            <td class="memory-actions">
                <button onclick="regenerateKey('${u.id}')" title="Regenerate API Key">Regenerate Key</button>
                <button onclick="deleteUser('${u.id}', '${escapeHtml(u.username)}')" title="Delete User" style="background:var(--color-danger)">Delete</button>
            </td>
        </tr>`).join('') +
        '</tbody></table>';

    container.innerHTML = html;
}

async function createUser() {
    const username = document.getElementById('new-username').value.trim();
    const password = document.getElementById('new-password').value;
    const role = document.getElementById('new-role').value;

    if (!username || !password) {
        alert('Username and password are required');
        return;
    }

    try {
        const response = await fetch('/api/admin/users?username=' + encodeURIComponent(username) + '&password=' + encodeURIComponent(password) + '&role=' + encodeURIComponent(role), {
            method: 'POST',
            headers: authHeaders()
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || 'Failed to create user');
        }

        document.getElementById('new-username').value = '';
        document.getElementById('new-password').value = '';
        loadUsers();
    } catch (error) {
        alert('Error creating user: ' + error.message);
    }
}

async function deleteUser(userId, username) {
    if (!confirm('Delete user "' + username + '"? This cannot be undone.')) return;

    try {
        const response = await fetch('/api/admin/users/' + userId, {
            method: 'DELETE',
            headers: authHeaders()
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || 'Failed to delete user');
        }

        loadUsers();
    } catch (error) {
        alert('Error deleting user: ' + error.message);
    }
}

async function regenerateKey(userId) {
    if (!confirm('Regenerate API key? The old key will stop working immediately.')) return;

    try {
        const response = await fetch('/api/admin/users/' + userId + '/regenerate-key', {
            method: 'POST',
            headers: authHeaders()
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || 'Failed to regenerate key');
        }

        loadUsers();
    } catch (error) {
        alert('Error: ' + error.message);
    }
}
