#!/usr/bin/env python3
"""Vérifie le proxy frontend et les écritures réelles en mode démo uniquement."""
import json
import os
from getpass import getpass
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

base = os.environ.get('SMOKE_BASE_URL', 'http://127.0.0.1:3000').rstrip('/')
opener = build_opener(HTTPCookieProcessor(CookieJar()))
origin = f'{urlsplit(base).scheme}://{urlsplit(base).netloc}'


def request(path, payload=None, method=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(base + path, data=data, method=method,
                  headers={'Content-Type': 'application/json', 'Origin': origin})
    with opener.open(req, timeout=90) as response:
        body = response.read().decode()
        return json.loads(body) if body else None


def main():
    with urlopen(base, timeout=30) as response:
        assert response.status == 200, 'Page frontend indisponible'
    try:
        with opener.open(base + '/api/conversations', timeout=30) as response:
            raise AssertionError(f'API privée accessible sans session ({response.status})')
    except HTTPError as exc:
        assert exc.code == 401, f'API privée refusée avec un statut inattendu ({exc.code})'
    username = os.environ.get('SMOKE_USERNAME') or input('Identifiant smoke test : ')
    password = os.environ.get('SMOKE_PASSWORD') or getpass('Mot de passe smoke test : ')
    request('/api/auth/login', {'username': username, 'password': password})
    health = request('/api/health')
    assert health['status'] == 'ok', health
    config = request('/api/config')
    assert config['models'], 'Aucun modèle configuré'
    if not config['demo_mode']:
        print('Frontend, proxy API, base et modèles OK. Test de génération omis : mode réel, aucun appel payant automatique.')
        return
    memory = conversation = None
    try:
        memory = request('/api/memories', {'content': 'Information temporaire du smoke test.'})
        conversation = request('/api/conversations', {'title': 'Vérification temporaire', 'model': config['default_model']})
        req = Request(base + '/api/conversations/' + conversation['id'] + '/messages',
                      data=json.dumps({'content': 'Bonjour, ceci est un test de démonstration.',
                                       'model': config['default_model'], 'web_search': False,
                                       'attachment_ids': []}).encode(),
                      headers={'Content-Type': 'application/json', 'Origin': origin})
        with opener.open(req, timeout=90) as response:
            stream = response.read().decode()
        assert 'event: delta' in stream, stream
        assert 'event: done' in stream and 'event: error' not in stream, stream
        saved = request('/api/conversations/' + conversation['id'])
        assert [m['role'] for m in saved['messages']] == ['user', 'assistant'], saved
        assert saved['messages'][1]['content'].strip(), saved
        assert any(m['id'] == memory['id'] for m in request('/api/memories'))
        print('Frontend + proxy + PostgreSQL/SQLite + mémoire + tchat SSE + historique : OK (réponses démo).')
    finally:
        if conversation:
            request('/api/conversations/' + conversation['id'], method='DELETE')
        if memory:
            request('/api/memories/' + memory['id'], method='DELETE')


if __name__ == '__main__':
    try:
        main()
    except (HTTPError, AssertionError) as exc:
        raise SystemExit(f'Échec de validation : {exc}') from exc
