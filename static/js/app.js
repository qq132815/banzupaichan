// ========== Common Utilities ==========
function toast(msg, type) {
    type = type || 'info';
    var c = document.getElementById('toast-container');
    var t = document.createElement('div');
    t.className = 'toast toast-' + type;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(function(){ t.style.opacity='0'; setTimeout(function(){ t.remove(); }, 300); }, 3000);
}

function api(url, options) {
    options = options || {};
    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
        options.headers = options.headers || {};
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(options.body);
    }
    return fetch(url, options).then(function(r) {
        if (!r.ok) {
            return r.json().then(function(e) { throw e; });
        }
        return r.json();
    });
}

function formatDate(d) {
    if (!d) return '';
    var dt = new Date(d);
    return dt.getFullYear() + '-' + String(dt.getMonth()+1).padStart(2,'0') + '-' + String(dt.getDate()).padStart(2,'0');
}

function priorityLabel(p) {
    if (p === 'P0') return '<span class="badge badge-red">P0 主机厂</span>';
    if (p === 'P1') return '<span class="badge badge-blue">P1 加工单</span>';
    return '<span class="badge badge-gray">P2 库存</span>';
}

function statusLabel(s) {
    var map = {planned:'已排',running:'进行中',completed:'已完成',cancelled:'已取消',pending:'待排'};
    return map[s] || s || '';
}

// Highlight active nav link
document.addEventListener('DOMContentLoaded', function() {
    var links = document.querySelectorAll('.nav-link');
    var path = window.location.pathname;
    links.forEach(function(a) {
        if (a.getAttribute('href') === path) {
            a.classList.add('active');
        }
    });
});
