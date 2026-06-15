# -*- coding: utf-8 -*-
import json
import time

from utils.ai_client import OpenAICompatibleClient, AIClientError
from utils.ai_knowledge import search_knowledge, rebuild_knowledge_index
from utils.ai_tools import run_relevant_tools
from utils.db import get_connection

SECRET_KEYS = set(['ai_api_key', 'ai_bot_feishu_secret', 'ai_bot_wechat_secret'])


def load_ai_settings(include_secrets=False):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM system_settings WHERE key LIKE 'ai_%'")
    rows = c.fetchall()
    conn.close()
    settings = {row['key']: row['value'] for row in rows}
    defaults = {
        'ai_enabled': '1',
        'ai_vector_store': 'chroma',
        'ai_chroma_mode': 'local',
        'ai_chroma_persist_dir': 'data/chroma',
        'ai_chroma_collection': 'production_ai_knowledge',
        'ai_request_timeout_seconds': '60',
        'ai_max_context_chunks': '5',
        'ai_max_tool_rows': '50',
        'ai_log_retention_days': '30'
    }
    for key, value in defaults.items():
        settings.setdefault(key, value)
    if not include_secrets:
        for key in SECRET_KEYS:
            if key in settings and settings[key]:
                settings[key] = '******'
    return settings


def save_ai_settings(data):
    allowed = set([
        'ai_enabled', 'ai_base_url', 'ai_api_key', 'ai_chat_model', 'ai_embedding_model',
        'ai_vector_store', 'ai_chroma_mode', 'ai_chroma_persist_dir', 'ai_chroma_host',
        'ai_chroma_port', 'ai_chroma_collection', 'ai_request_timeout_seconds',
        'ai_max_context_chunks', 'ai_max_tool_rows', 'ai_log_retention_days',
        'ai_bot_feishu_enabled', 'ai_bot_feishu_secret', 'ai_bot_wechat_enabled',
        'ai_bot_wechat_secret'
    ])
    conn = get_connection()
    c = conn.cursor()
    for key, value in (data or {}).items():
        if key not in allowed:
            continue
        if key in SECRET_KEYS and value == '******':
            continue
        c.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, datetime('now','localtime'))", (key, str(value)))
    conn.commit()
    conn.close()


def build_context(session_data):
    return {
        'user_id': session_data.get('user_id'),
        'username': session_data.get('username'),
        'display_name': session_data.get('display_name'),
        'role': session_data.get('role'),
        'team_id': session_data.get('team_id')
    }


def _log_chat(ctx, channel, question, answer, tools_used, knowledge_sources, model, success, error, latency_ms):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO ai_chat_logs
                     (user_id, role, team_id, channel, question, answer, tools_used,
                      knowledge_sources, model, success, error, latency_ms)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (ctx.get('user_id'), ctx.get('role'), ctx.get('team_id'), channel,
                   question, answer, json.dumps(tools_used, ensure_ascii=False),
                   json.dumps(knowledge_sources, ensure_ascii=False), model,
                   1 if success else 0, error, latency_ms))
        conn.commit()
        conn.close()
    except Exception:
        pass


def run_chat(question, ctx, channel='web'):
    started = time.time()
    settings = load_ai_settings(include_secrets=True)
    answer = ''
    tools_used = []
    knowledge_sources = []
    error = ''
    try:
        if str(settings.get('ai_enabled', '1')) not in ('1', 'true', 'True', 'yes', 'on'):
            raise AIClientError('AI 助手未启用')
        question = (question or '').strip()
        if not question:
            raise AIClientError('问题不能为空')

        knowledge = search_knowledge(question, settings)
        chunks = knowledge.get('chunks') or []
        knowledge_warning = knowledge.get('warning') or ''
        knowledge_sources = [{'source_path': c.get('source_path'), 'title': c.get('title')} for c in chunks]

        tool_results = run_relevant_tools(question, ctx, settings)
        tools_used = [r.get('name') for r in tool_results]
        prompt_context = {
            'user_role': ctx.get('role'),
            'user_team_id': ctx.get('team_id'),
            'knowledge_warning': knowledge_warning,
            'knowledge_chunks': chunks,
            'tool_results': tool_results
        }
        system_prompt = (
            '你是制造企业 MES 班组排产系统的只读 AI 助手。'
            '必须基于提供的数据库工具结果和知识库片段回答。'
            '不要编造数量、日期、工单状态。没有数据就明确说没有查到。'
            '班组用户只能看本班组数据；不要泄露密码、API Key、系统密钥。'
            '回答要中文、简洁、可执行。'
        )
        user_prompt = '用户问题：%s\n\n可用上下文 JSON：\n%s' % (question, json.dumps(prompt_context, ensure_ascii=False, default=str)[:24000])
        client = OpenAICompatibleClient(settings)
        answer = client.chat([
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ])
        if knowledge_warning:
            answer += '\n\n提示：文档向量检索暂不可用或不完整：' + knowledge_warning
        latency = int((time.time() - started) * 1000)
        _log_chat(ctx, channel, question, answer, tools_used, knowledge_sources, settings.get('ai_chat_model'), True, '', latency)
        return {'ok': True, 'answer': answer, 'tools_used': tools_used, 'knowledge_sources': knowledge_sources, 'latency_ms': latency}
    except Exception as exc:
        error = str(exc)
        latency = int((time.time() - started) * 1000)
        answer = 'AI 助手暂时无法回答：' + error
        _log_chat(ctx, channel, question, answer, tools_used, knowledge_sources, settings.get('ai_chat_model'), False, error, latency)
        return {'ok': False, 'error': error, 'answer': answer, 'tools_used': tools_used, 'knowledge_sources': knowledge_sources, 'latency_ms': latency}


def rebuild_index():
    settings = load_ai_settings(include_secrets=True)
    return rebuild_knowledge_index(settings)


def get_chat_logs(limit=100):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT l.id, l.user_id, u.display_name, l.role, l.team_id, t.name AS team_name,
                        l.channel, l.question, l.answer, l.tools_used, l.knowledge_sources,
                        l.model, l.success, l.error, l.latency_ms, l.created_at
                 FROM ai_chat_logs l
                 LEFT JOIN users u ON l.user_id=u.id
                 LEFT JOIN teams t ON l.team_id=t.id
                 ORDER BY l.id DESC LIMIT ?''', (int(limit or 100),))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows
