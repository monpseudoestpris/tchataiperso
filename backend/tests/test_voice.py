"""Tests unitaires et d'intégration pour la synthèse vocale (Google TTS) et la dictée (Mistral Voxtral / Google STT)."""

from __future__ import annotations

import base64
import io
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.voice import pcm_to_wav, resolve_stt_provider
from app.voice_sanitize import prepare_text_for_speech, split_speech_chunks


def _make_settings(tmp_path: Path, **overrides) -> Settings:
    data = {
        "_env_file": None,
        "app_data_dir": tmp_path,
        "demo_mode": True,
        "cors_origins": "http://localhost:3001",
    }
    data.update(overrides)
    return Settings(**data)


def _setup_client(tmp_path: Path, **settings_overrides) -> TestClient:
    settings = _make_settings(tmp_path, **settings_overrides)
    app = create_app(settings)
    from app.auth import hash_password
    from app.models import Base, User

    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        db.add(
            User(
                username="alice",
                password_hash=hash_password("SuperSecret123!"),
                is_admin=True,
                active=True,
            )
        )
        db.commit()

    client = TestClient(app)
    resp = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "SuperSecret123!"},
        headers={"origin": "http://localhost:3001"},
    )
    assert resp.status_code == 200
    return client


def test_prepare_text_for_speech_filters_images_citations_code_and_urls():
    raw = """
## Règle du tour [p. 4]

![Schéma du plateau](/api/docs/toy-fr01/p4_fig1.webp)
<figure><img src="/api/docs/toy-fr01/page_4.webp" /><figcaption>Page 4</figcaption></figure>

Chaque joueur pioche **2 cartes** [1, 2] puis consulte [le guide officiel](https://example.com/guide).
Voir aussi https://example.com/raw-link et `/api/docs/toy-fr01/p4_fig1.webp`.

```python
def score(x):
    return x * 2
```

| Action | Coût |
| --- | --- |
| Attaquer | 2 |

Formule : $$E = mc^2$$ et bonus $2 \\times 3$.

[^1]: Source officielle p. 4
"""
    cleaned = prepare_text_for_speech(raw)
    assert "/api/docs" not in cleaned
    assert "p4_fig1" not in cleaned
    assert "[p. 4]" not in cleaned
    assert "[1, 2]" not in cleaned
    assert "https://" not in cleaned
    assert "def score" not in cleaned
    assert "| Action |" not in cleaned
    assert "[^1]" not in cleaned
    assert "Règle du tour." in cleaned
    assert "Chaque joueur pioche 2 cartes puis consulte le guide officiel." in cleaned
    assert "Le bloc de code est affiché à l'écran." in cleaned
    assert "Voir le tableau affiché." in cleaned
    assert "2 fois 3" in cleaned

    # Élisions françaises et apostrophes typographiques (ex: "l' **écouteur**" ou "l’écouteur")
    elision_cleaned = prepare_text_for_speech("Branchez l’ **écouteur** sur d' `autres` prises qu’ il choisit.")
    assert "l'écouteur" in elision_cleaned
    assert "d'autres" in elision_cleaned
    assert "qu'il" in elision_cleaned

    # Backticks orphelins et guillemets ne doivent jamais atteindre le moteur TTS
    quotes_cleaned = prepare_text_for_speech("Texte avec `backtick orphelin, « guillemets », 'citation' et l'écouteur.")
    assert "`" not in quotes_cleaned
    assert "«" not in quotes_cleaned
    assert "»" not in quotes_cleaned
    assert "'citation'" not in quotes_cleaned
    assert "citation" in quotes_cleaned
    assert "l'écouteur" in quotes_cleaned


def test_split_speech_chunks_respects_sentence_boundaries():
    text = "\n".join(f"Phrase numéro {i} avec un contenu clair." for i in range(40))
    chunks = split_speech_chunks(text, max_chunk_chars=250)
    assert len(chunks) > 2
    assert all(len(c) <= 250 for c in chunks)
    assert "Phrase numéro 0" in chunks[0]
    assert "Phrase numéro 39" in chunks[-1]


def test_pcm_to_wav_produces_valid_24khz_mono_header():
    pcm = b"\x00\x01" * 240
    wav_bytes = pcm_to_wav(pcm, sample_rate=24000)
    assert wav_bytes.startswith(b"RIFF")
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 24000
        assert wf.getnframes() == 240


def test_resolve_stt_provider_priority(tmp_path: Path):
    s_mistral_and_google = _make_settings(
        tmp_path,
        demo_mode=False,
        mistral_api_key=SecretStr("m-key"),
        google_api_key=SecretStr("g-key"),
        stt_provider="auto",
    )
    assert resolve_stt_provider(s_mistral_and_google) == "mistral"
    assert resolve_stt_provider(s_mistral_and_google, requested="google") == "google"

    s_google_only = _make_settings(
        tmp_path,
        demo_mode=False,
        google_api_key=SecretStr("g-key"),
        stt_provider="auto",
    )
    assert resolve_stt_provider(s_google_only) == "google"


def test_voice_endpoints_in_demo_mode(tmp_path: Path):
    with _setup_client(tmp_path, demo_mode=True) as client:
        cfg = client.get("/api/config").json()
        assert cfg["features"]["tts"] is True
        assert cfg["features"]["stt"] is True
        assert cfg["voice"]["default_voice"] == "Aoede"
        assert len(cfg["voice"]["voices"]) == 30

        tts_resp = client.post(
            "/api/voice/tts",
            json={"text": "Bonjour ! ![fig](/api/docs/x/p1_fig1.webp) [p. 2]", "voice": "Kore"},
            headers={"origin": "http://localhost:3001"},
        )
        assert tts_resp.status_code == 200
        assert tts_resp.headers["content-type"].startswith("audio/wav")
        assert tts_resp.content.startswith(b"RIFF")

        # Texte uniquement composé d'images/références -> 400
        empty_resp = client.post(
            "/api/voice/tts",
            json={"text": "![fig](/api/docs/x/p1_fig1.webp) [p. 2]"},
            headers={"origin": "http://localhost:3001"},
        )
        assert empty_resp.status_code == 400

        # Transcription valide en mode démo
        stt_resp = client.post(
            "/api/voice/transcribe",
            files={"file": ("dictation.webm", b"OggS-fake-audio-bytes", "audio/webm")},
            data={"language": "fr"},
            headers={"origin": "http://localhost:3001"},
        )
        assert stt_resp.status_code == 200
        assert stt_resp.json()["provider"] == "demo"
        assert stt_resp.json()["text"]

        # Rejet MIME non audio
        bad_mime = client.post(
            "/api/voice/transcribe",
            files={"file": ("evil.exe", b"MZ-not-audio", "application/octet-stream")},
            headers={"origin": "http://localhost:3001"},
        )
        assert bad_mime.status_code == 400


def test_voice_tts_and_stt_real_mode_mocked(tmp_path: Path):
    pcm_payload = base64.b64encode(b"\x01\x02" * 100).decode("ascii")
    fake_tts_response = AsyncMock()
    fake_tts_response.is_success = True
    fake_tts_response.status_code = 200
    fake_tts_response.json = lambda: {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "audio/L16;codec=pcm;rate=24000",
                                "data": pcm_payload,
                            }
                        }
                    ]
                }
            }
        ]
    }

    fake_stt_response = AsyncMock()
    fake_stt_response.is_success = True
    fake_stt_response.status_code = 200
    fake_stt_response.json = lambda: {"text": "Explique-moi cette règle de jeu."}

    with _setup_client(
        tmp_path,
        demo_mode=False,
        google_api_key=SecretStr("AIzaFakeKeyForUnitTest"),
        mistral_api_key=SecretStr("FakeMistralKeyForUnitTest"),
    ) as client:
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_tts_response)) as mock_tts:
            r = client.post(
                "/api/voice/tts",
                json={"text": "Bonjour **monde** [p. 1]", "voice": "Aoede", "tone": "warm"},
                headers={"origin": "http://localhost:3001"},
            )
            assert r.status_code == 200
            assert r.content.startswith(b"RIFF")
            assert mock_tts.await_count == 1
            called_url = mock_tts.await_args.args[0]
            assert "gemini-2.5-flash-tts:generateContent" in called_url
            sent_text = mock_tts.await_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
            assert sent_text.startswith("Say warmly, smiling, and naturally in French: ")
            assert "Bonjour monde." in sent_text

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_stt_response)) as mock_stt:
            r = client.post(
                "/api/voice/transcribe",
                files={"file": ("dictation.webm", b"webm-audio-data", "audio/webm;codecs=opus")},
                data={"language": "fr"},
                headers={"origin": "http://localhost:3001"},
            )
            assert r.status_code == 200
            payload = r.json()
            assert payload["provider"] == "mistral"
            assert payload["text"] == "Explique-moi cette règle de jeu."
            called_url = mock_stt.await_args.args[0]
            assert called_url == "https://api.mistral.ai/v1/audio/transcriptions"


def test_voice_tts_prioritizes_vertex_oauth_and_falls_back_on_402(tmp_path: Path):
    pcm_payload = base64.b64encode(b"\x01\x02" * 100).decode("ascii")
    resp_402 = AsyncMock()
    resp_402.is_success = False
    resp_402.status_code = 402
    resp_402.json = lambda: {"error": {"message": "Payment required"}}

    resp_ok = AsyncMock()
    resp_ok.is_success = True
    resp_ok.status_code = 200
    resp_ok.json = lambda: {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "audio/L16;codec=pcm;rate=24000",
                                "data": pcm_payload,
                            }
                        }
                    ]
                }
            }
        ]
    }

    with _setup_client(
        tmp_path,
        demo_mode=False,
        google_cloud_mode="vertex_oauth",
        google_cloud_project="my-test-project",
        google_cloud_location="global",
        google_api_key=SecretStr("AIzaFakeKeyForUnitTest"),
    ) as client:
        with (
            patch(
                "app.voice.get_google_cloud_access_token",
                new=AsyncMock(return_value=("ya29.fake-token", "my-test-project")),
            ),
            patch(
                "httpx.AsyncClient.post",
                new=AsyncMock(side_effect=[resp_402, resp_ok]),
            ) as mock_post,
        ):
            r = client.post(
                "/api/voice/tts",
                json={"text": "Test Vertex OAuth", "voice": "Aoede"},
                headers={"origin": "http://localhost:3001"},
            )
            assert r.status_code == 200
            assert r.content.startswith(b"RIFF")
            assert mock_post.await_count == 2
            first_url = mock_post.await_args_list[0].args[0]
            assert "us-central1-aiplatform.googleapis.com/v1/projects/my-test-project/locations/us-central1/publishers/google/models/gemini-2.5-flash-tts:generateContent" in first_url
