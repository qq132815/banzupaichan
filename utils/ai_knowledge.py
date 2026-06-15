# -*- coding: utf-8 -*-
import hashlib
import os
import re

from utils.ai_client import OpenAICompatibleClient, AIClientError
from utils.db import get_connection

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_COLLECTION = 'production_ai_knowledge'


def _safe_rel(path):
    try:
        return os.path.relpath(path, PROJECT_ROOT).replace('\\', '/')
    except Exception:
        return path


def _content_hash(text):
    return hashlib.sha256((text or '').encode('utf-8')).hexdigest()


def _iter_knowledge_files():
    names = [
        'AGENTS.md',
        'documentation.md',
        'GANTT_CHART_DESIGN.md',
    ]
    for name in names:
        path = os.path.join(PROJECT_ROOT, name)
        if os.path.exists(path):
            yield path
    for name in os.listdir(PROJECT_ROOT):
        if name.endswith('.md') and name not in names:
            yield os.path.join(PROJECT_ROOT, name)
    specs_dir = os.path.join(PROJECT_ROOT, 'docs', 'superpowers', 'specs')
    if os.path.isdir(specs_dir):
        for name in os.listdir(specs_dir):
            if name.endswith('.md'):
                yield os.path.join(specs_dir, name)


def _read_text(path):
    with open(path, 'r', encoding='utf-8-sig') as f:
        return f.read()


def _chunk_text(text, max_chars=900):
    text = (text or '').strip()
    if not text:
        return []
    parts = re.split(r'(?m)^(#{1,6}\s+.+)$', text)
    sections = []
    current_title = ''
    current_body = ''
    for part in parts:
        if not part:
            continue
        if re.match(r'^#{1,6}\s+', part):
            if current_body.strip():
                sections.append((current_title, current_body.strip()))
            current_title = part.strip('# ').strip()
            current_body = ''
        else:
            current_body += '\n' + part
    if current_body.strip():
        sections.append((current_title, current_body.strip()))
    if not sections:
        sections = [('', text)]

    chunks = []
    for title, body in sections:
        body = body.strip()
        while len(body) > max_chars:
            cut = body.rfind('\n', 0, max_chars)
            if cut < 300:
                cut = max_chars
            chunks.append((title, body[:cut].strip()))
            body = body[cut:].strip()
        if body:
            chunks.append((title, body))
    return chunks


def _load_chroma(settings):
    try:
        import chromadb
    except Exception as exc:
        raise RuntimeError('chromadb 未安装，请先安装 requirements.txt 中的 chromadb: ' + str(exc))

    mode = settings.get('ai_chroma_mode') or 'local'
    collection_name = settings.get('ai_chroma_collection') or DEFAULT_COLLECTION
    if mode == 'http':
        host = settings.get('ai_chroma_host') or 'localhost'
        try:
            port = int(settings.get('ai_chroma_port') or 8000)
        except Exception:
            port = 8000
        client = chromadb.HttpClient(host=host, port=port)
    else:
        persist_dir = settings.get('ai_chroma_persist_dir') or os.path.join(PROJECT_ROOT, 'data', 'chroma')
        client = chromadb.PersistentClient(path=persist_dir)
    return client.get_or_create_collection(name=collection_name), collection_name


def search_knowledge(question, settings, limit=None):
    if not question:
        return {'chunks': [], 'warning': ''}
    if (settings.get('ai_vector_store') or 'chroma') != 'chroma':
        return {'chunks': [], 'warning': '当前仅实现 Chroma 向量检索'}
    try:
        topn = int(limit or settings.get('ai_max_context_chunks') or 5)
    except Exception:
        topn = 5
    try:
        client = OpenAICompatibleClient(settings)
        query_vector = client.embed(question)
        collection, collection_name = _load_chroma(settings)
        result = collection.query(query_embeddings=[query_vector], n_results=topn, include=['documents', 'metadatas', 'distances'])
        docs = result.get('documents') or [[]]
        metas = result.get('metadatas') or [[]]
        distances = result.get('distances') or [[]]
        chunks = []
        for i, doc in enumerate(docs[0]):
            meta = metas[0][i] if i < len(metas[0]) else {}
            dist = distances[0][i] if i < len(distances[0]) else None
            chunks.append({
                'content': doc,
                'source_path': meta.get('source_path', ''),
                'title': meta.get('title', ''),
                'distance': dist,
                'collection': collection_name
            })
        return {'chunks': chunks, 'warning': ''}
    except Exception as exc:
        return {'chunks': [], 'warning': str(exc)}


def rebuild_knowledge_index(settings):
    if (settings.get('ai_vector_store') or 'chroma') != 'chroma':
        raise RuntimeError('当前仅支持 Chroma 知识库重建')
    client = OpenAICompatibleClient(settings)
    collection, collection_name = _load_chroma(settings)
    conn = get_connection()
    c = conn.cursor()
    total_docs = 0
    total_chunks = 0
    for path in _iter_knowledge_files():
        try:
            text = _read_text(path)
        except Exception:
            continue
        rel = _safe_rel(path)
        doc_hash = _content_hash(text)
        title = os.path.basename(path)
        c.execute('SELECT id, content_hash FROM ai_knowledge_docs WHERE source_path=?', (rel,))
        row = c.fetchone()
        if row and row['content_hash'] == doc_hash:
            continue
        if row:
            doc_id = row['id']
            c.execute('UPDATE ai_knowledge_docs SET title=?, content_hash=?, updated_at=datetime(\'now\',\'localtime\') WHERE id=?', (title, doc_hash, doc_id))
            c.execute('DELETE FROM ai_knowledge_chunks WHERE doc_id=?', (doc_id,))
        else:
            c.execute('INSERT INTO ai_knowledge_docs (source_path, title, content_hash) VALUES (?,?,?)', (rel, title, doc_hash))
            doc_id = c.lastrowid
        total_docs += 1
        chunks = _chunk_text(text)
        for idx, (chunk_title, content) in enumerate(chunks):
            chunk_hash = _content_hash(content)
            chroma_id = '%s:%s:%s' % (rel, idx, chunk_hash[:12])
            vector = client.embed(content)
            metadata = {
                'source_path': rel,
                'title': chunk_title or title,
                'chunk_index': idx,
                'content_hash': chunk_hash
            }
            collection.upsert(ids=[chroma_id], embeddings=[vector], documents=[content], metadatas=[metadata])
            c.execute('''INSERT INTO ai_knowledge_chunks
                         (doc_id, chunk_index, title, content, chroma_collection, chroma_id, content_hash)
                         VALUES (?,?,?,?,?,?,?)''',
                      (doc_id, idx, chunk_title or title, content, collection_name, chroma_id, chunk_hash))
            total_chunks += 1
        conn.commit()
    conn.close()
    return {'docs_indexed': total_docs, 'chunks_indexed': total_chunks, 'collection': collection_name}
