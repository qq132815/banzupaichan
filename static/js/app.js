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


// ========== Pagination ==========
function goToPage(p, funcName) {
    window._page = parseInt(p);
    window[funcName]();
}
function changePageSize(size, funcName) {
    window._pageSize = parseInt(size);
    window._page = 1;
    window[funcName]();
}
function renderPagination(containerId, currentPage, totalPages, funcName) {
    var c = document.getElementById(containerId);
    if (!c) return;
    var html = '<div class="pagination-wrap">';
    html += '<select class="pagination-size" onchange="changePageSize(this.value,\''+funcName+'\')">';
    [20,50,100,200].forEach(function(n){
        html += '<option value="'+n+'"'+(window._pageSize===n?' selected':'')+'>'+n+'/页</option>';
    });
    html += '</select>';
    html += '<div class="pagination-btns">';
    html += '<button class="btn-page" '+ (currentPage<=1?'disabled':'') +' onclick="goToPage('+(currentPage-1)+',\''+funcName+'\')">‹</button>';
    var start = Math.max(1, currentPage - 2);
    var end = Math.min(totalPages, currentPage + 2);
    if (start > 1) {
        html += '<button class="btn-page" onclick="goToPage(1,\''+funcName+'\')">1</button>';
        if (start > 2) html += '<span class="page-ellipsis">...</span>';
    }
    for (var i = start; i <= end; i++) {
        html += '<button class="btn-page'+(i===currentPage?' active':'')+'" onclick="goToPage('+i+',\''+funcName+'\')">'+i+'</button>';
    }
    if (end < totalPages) {
        if (end < totalPages - 1) html += '<span class="page-ellipsis">...</span>';
        html += '<button class="btn-page" onclick="goToPage('+totalPages+',\''+funcName+'\')">'+totalPages+'</button>';
    }
    html += '<button class="btn-page" '+ (currentPage>=totalPages?'disabled':'') +' onclick="goToPage('+(currentPage+1)+',\''+funcName+'\')">›</button>';
    html += '</div>';
    html += '<span class="pagination-info">共 '+window._total+' 条</span>';
    html += '</div>';
    c.innerHTML = html;
}

// ========== Import Modal ==========
function showImportModal(apiUrl, onSuccess) {
    // Create modal if not exists
    var overlay = document.getElementById('import-modal-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'import-modal-overlay';
        overlay.className = 'modal-overlay';
        overlay.innerHTML = '<div class="modal" style="max-width:480px">'
            + '<div class="modal-header"><h3>导入数据</h3><button class="modal-close" onclick="closeImportModal()">&times;</button></div>'
            + '<div class="modal-body">'
            + '<div id="import-step1">'
            + '<p style="color:#6b7280;font-size:13px;margin-bottom:16px">选择 Excel 文件，系统将自动匹配表头字段</p>'
            + '<div style="border:2px dashed #d1d5db;border-radius:8px;padding:24px;text-align:center;cursor:pointer" id="import-dropzone" onclick="document.getElementById(\'import-file-input\').click()">'
            + '<div style="font-size:32px;margin-bottom:8px">📤</div>'
            + '<div style="color:#374151;font-weight:600">点击选择文件或拖拽到此处</div>'
            + '<div style="color:#9ca3af;font-size:12px;margin-top:4px">支持 .xlsx / .xls 格式</div>'
            + '<input type="file" id="import-file-input" accept=".xlsx,.xls" style="display:none" onchange="onImportFileSelect(this)">'
            + '</div>'
            + '<div id="import-file-info" style="display:none;margin-top:12px;padding:8px 12px;background:#f0fdf4;border-radius:6px;font-size:13px;color:#166534"></div>'
            + '</div>'
            + '<div id="import-step2" style="display:none;text-align:center;padding:20px">'
            + '<div style="font-size:24px;margin-bottom:8px">⏳</div>'
            + '<div style="font-weight:600;margin-bottom:8px">正在导入...</div>'
            + '<div style="background:#e5e7eb;border-radius:4px;height:6px;overflow:hidden"><div id="import-progress" style="background:#3b82f6;height:100%;width:0%;transition:width 0.3s"></div></div>'
            + '</div>'
            + '<div id="import-step3" style="display:none;text-align:center;padding:20px">'
            + '<div id="import-result-icon" style="font-size:32px;margin-bottom:8px"></div>'
            + '<div id="import-result-msg" style="font-weight:600;margin-bottom:16px"></div>'
            + '</div>'
            + '</div>'
            + '<div class="modal-footer" id="import-footer">'
            + '<button class="btn btn-secondary" onclick="closeImportModal()">取消</button>'
            + '<button class="btn btn-primary" id="import-submit-btn" onclick="submitImport()" disabled>导入</button>'
            + '</div>'
            + '</div>';
        document.body.appendChild(overlay);
    }
    window._importApiUrl = apiUrl;
    window._importOnSuccess = onSuccess;
    window._importFile = null;
    // Reset state
    document.getElementById('import-step1').style.display = '';
    document.getElementById('import-step2').style.display = 'none';
    document.getElementById('import-step3').style.display = 'none';
    document.getElementById('import-file-info').style.display = 'none';
    document.getElementById('import-submit-btn').disabled = true;
    document.getElementById('import-submit-btn').style.display = '';
    document.getElementById('import-footer').style.display = '';
    document.getElementById('import-file-input').value = '';
    document.querySelector('#import-footer .btn-secondary').textContent = '取消';
    overlay.classList.add('show');
}

function closeImportModal() {
    var overlay = document.getElementById('import-modal-overlay');
    if (overlay) overlay.classList.remove('show');
}

function onImportFileSelect(input) {
    var f = input.files[0];
    if (!f) return;
    window._importFile = f;
    var info = document.getElementById('import-file-info');
    info.style.display = '';
    info.innerHTML = '📎 ' + f.name + ' (' + (f.size/1024).toFixed(1) + 'KB)';
    document.getElementById('import-submit-btn').disabled = false;
    // Drag zone highlight
    var dz = document.getElementById('import-dropzone');
    if (dz) dz.style.borderColor = '#10b981';
}

function submitImport() {
    var f = window._importFile;
    if (!f) return;
    document.getElementById('import-step1').style.display = 'none';
    document.getElementById('import-step2').style.display = '';
    document.getElementById('import-footer').style.display = 'none';
    document.getElementById('import-progress').style.width = '50%';
    var fd = new FormData();
    fd.append('file', f);
    fetch(window._importApiUrl, {method:'POST', body:fd, credentials:'same-origin'})
    .then(function(resp) {
        document.getElementById('import-progress').style.width = '100%';
        return resp.json();
    })
    .then(function(d) {
        setTimeout(function() {
            document.getElementById('import-step2').style.display = 'none';
            document.getElementById('import-step3').style.display = '';
            var ri = document.getElementById('import-result-icon');
            var rm = document.getElementById('import-result-msg');
            document.getElementById('import-footer').style.display = '';
            document.getElementById('import-submit-btn').style.display = 'none';
            document.querySelector('#import-footer .btn-secondary').textContent = '\u5173\u95ed';
            if (d.success) {
                ri.textContent = '\u2705';
                rm.textContent = '\u5bfc\u5165\u6210\u529f\uff0c\u5171 ' + d.count + ' \u6761\u6570\u636e';
                rm.style.color = '#059669';
                console.log('Import success, calling callback', d); if (window._importOnSuccess) { console.log('Callback found'); window._importOnSuccess(d); } else { console.log('No callback'); }
            } else {
                ri.textContent = '\u274c';
                rm.textContent = d.error || '\u5bfc\u5165\u5931\u8d25';
                rm.style.color = '#dc2626';
            }
        }, 300);
    })
    .catch(function(err) {
        setTimeout(function() {
            document.getElementById('import-step2').style.display = 'none';
            document.getElementById('import-step3').style.display = '';
            document.getElementById('import-result-icon').textContent = '\u274c';
            document.getElementById('import-result-msg').textContent = '\u5bfc\u5165\u5931\u8d25: ' + err.message;
            document.getElementById('import-result-msg').style.color = '#dc2626';
            document.getElementById('import-footer').style.display = '';
            document.getElementById('import-submit-btn').style.display = 'none';
            document.querySelector('#import-footer .btn-secondary').textContent = '\u5173\u95ed';
        }, 300);
    });
}

// Setup drag & drop
document.addEventListener('DOMContentLoaded', function() {
    document.addEventListener('dragover', function(e) {
        if (document.getElementById('import-dropzone')) {
            e.preventDefault();
            document.getElementById('import-dropzone').style.borderColor = '#3b82f6';
        }
    });
    document.addEventListener('drop', function(e) {
        var dz = document.getElementById('import-dropzone');
        if (dz) {
            e.preventDefault();
            dz.style.borderColor = '#d1d5db';
            if (e.dataTransfer.files.length) {
                var input = document.getElementById('import-file-input');
                input.files = e.dataTransfer.files;
                onImportFileSelect(input);
            }
        }
    });
});
