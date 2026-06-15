# -*- coding: utf-8 -*-
import json


class AIClientError(Exception):
    pass


class OpenAICompatibleClient(object):
    def __init__(self, settings):
        self.base_url = (settings.get('ai_base_url') or '').rstrip('/')
        self.api_key = settings.get('ai_api_key') or ''
        self.chat_model = settings.get('ai_chat_model') or ''
        self.embedding_model = settings.get('ai_embedding_model') or ''
        try:
            self.timeout = int(settings.get('ai_request_timeout_seconds') or 60)
        except Exception:
            self.timeout = 60

    def _headers(self):
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = 'Bearer ' + self.api_key
        return headers

    def _require_base_url(self):
        if not self.base_url:
            raise AIClientError('AI base URL 未配置')

    def chat(self, messages, temperature=0.2):
        try:
            import requests
        except Exception as exc:
            raise AIClientError('requests 未安装，请先安装 requirements.txt: ' + str(exc))
        self._require_base_url()
        if not self.chat_model:
            raise AIClientError('AI chat model 未配置')
        payload = {
            'model': self.chat_model,
            'messages': messages,
            'temperature': temperature
        }
        url = self.base_url + '/chat/completions'
        try:
            resp = requests.post(url, headers=self._headers(), data=json.dumps(payload), timeout=self.timeout)
        except requests.RequestException as exc:
            raise AIClientError('调用 Qwen3.5 失败: ' + str(exc))
        if resp.status_code >= 400:
            raise AIClientError('调用 Qwen3.5 失败: HTTP %s %s' % (resp.status_code, resp.text[:300]))
        data = resp.json()
        try:
            return data['choices'][0]['message']['content']
        except Exception:
            raise AIClientError('Qwen3.5 返回格式无法识别')

    def embed(self, texts):
        try:
            import requests
        except Exception as exc:
            raise AIClientError('requests 未安装，请先安装 requirements.txt: ' + str(exc))
        self._require_base_url()
        if not self.embedding_model:
            raise AIClientError('Embedding model 未配置')
        single = isinstance(texts, str)
        inputs = [texts] if single else list(texts)
        payload = {
            'model': self.embedding_model,
            'input': inputs
        }
        url = self.base_url + '/embeddings'
        try:
            resp = requests.post(url, headers=self._headers(), data=json.dumps(payload), timeout=self.timeout)
        except requests.RequestException as exc:
            raise AIClientError('调用 Embedding 模型失败: ' + str(exc))
        if resp.status_code >= 400:
            raise AIClientError('调用 Embedding 模型失败: HTTP %s %s' % (resp.status_code, resp.text[:300]))
        data = resp.json()
        try:
            vectors = [item['embedding'] for item in data['data']]
        except Exception:
            raise AIClientError('Embedding 返回格式无法识别')
        return vectors[0] if single else vectors
