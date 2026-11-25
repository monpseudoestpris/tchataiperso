from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..api_key_tester import probe_provider_api_key
from ..api_key_vault import (
    EXTERNAL_API_KEY_SPECS,
    ApiKeyVault,
    VaultConfigurationError,
    validate_vault_key_name,
)
from ..auth import verify_password
from ..base_prompt import BASE_USER_PROMPT
from ..config import Settings
from ..deps import current_user, get_sessions, get_settings, require_admin
from ..models import User
from ..schemas import (
     DEFAULT_PROMPT_PRESETS,
    AdminApiKeyItem,
    AdminApiKeysResponse,
    TestAdminApiKeyRequest,
    TestAdminApiKeyResponse,
    UpdateAdminApiKeysRequest,
    UpdateUserSettingsRequest,
    UserSettingsResponse,
)
from ..serializers import stamp
from ..voice import is_valid_voice_id, resolve_voice_name

router = APIRouter(tags=["settings"])

_SUDO_WINDOW_SECONDS = 60.0
_SUDO_MAX_ATTEMPTS = 8


def _get_vault(request: Request, sessions: sessionmaker, settings: Settings) -> ApiKeyVault:
    vault = getattr(request.app.state, "vault", None)
    if isinstance(vault, ApiKeyVault):
        return vault
    vault = ApiKeyVault(sessions=sessions, app_data_dir=settings.app_data_dir)
    request.app.state.vault = vault
    settings.attach_vault(vault)
    return vault


def _verify_admin_sudo(
    request: Request,
    sessions: sessionmaker,
    admin: User,
    current_password: str,
) -> None:
    """Vérifie le mot de passe actuel de l'administrateur avec limitation anti-bruteforce."""
    if not hasattr(request.app.state, "sudo_failures"):
        request.app.state.sudo_failures = {}
    sudo_failures: dict[str, tuple[int, float]] = request.app.state.sudo_failures

    now_mono = monotonic()
    if len(sudo_failures) > 1024:
        for bucket, (_, started_at) in list(sudo_failures.items()):
            if now_mono - started_at >= _SUDO_WINDOW_SECONDS:
                sudo_failures.pop(bucket, None)

    host = request.client.host if request.client else "unknown"
    bucket_key = f"{admin.id}:{host}"
    attempts, window_start = sudo_failures.get(bucket_key, (0, now_mono))
    if now_mono - window_start >= _SUDO_WINDOW_SECONDS:
        attempts, window_start = 0, now_mono
    if attempts >= _SUDO_MAX_ATTEMPTS:
        raise HTTPException(
            429,
            "Trop de tentatives de confirmation du mot de passe. Réessayez dans une minute.",
        )

    with sessions() as db:
        db_admin = db.get(User, admin.id)
        if (
            not db_admin
            or not db_admin.active
            or not db_admin.is_admin
            or not verify_password(current_password, db_admin.password_hash)
        ):
            sudo_failures[bucket_key] = (attempts + 1, window_start)
            raise HTTPException(401, "Mot de passe administrateur incorrect.")

    sudo_failures.pop(bucket_key, None)


def _build_admin_api_keys_response(settings: Settings, vault: ApiKeyVault) -> AdminApiKeysResponse:
    settings.refresh_from_env_file()
    timestamps = vault.list_override_timestamps()
    items: list[AdminApiKeyItem] = []
    for spec in EXTERNAL_API_KEY_SPECS:
        origin = settings.api_key_origin(spec.key_name)
        updated_dt = timestamps.get(spec.key_name) if origin == "active_vault" else None
        items.append(
            AdminApiKeyItem(
                key_name=spec.key_name,
                env_name=spec.env_name,
                label=spec.label,
                description=spec.description,
                is_llm_key=spec.is_llm_key,
                status=origin,
                has_env_fallback=settings.has_env_fallback(spec.key_name),
                updated_at=stamp(updated_dt) if updated_dt else None,
            )
        )
    return AdminApiKeysResponse(
        demo_mode=bool(settings.demo_mode),
        baseline_demo_mode=bool(settings._baseline_demo_mode),
        items=items,
    )


@router.get("/api/settings", response_model=UserSettingsResponse)
def get_user_settings(
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    """Retrieve the current user's general prompt, caching preference, voice and presets."""
    effective_prompt = (getattr(user, "system_prompt", "") or "").strip() or BASE_USER_PROMPT
    effective_voice = resolve_voice_name(settings, getattr(user, "default_voice", None))
    return UserSettingsResponse(
        system_prompt=effective_prompt,
        prompt_cache_enabled=getattr(user, "prompt_cache_enabled", True),
        auto_memory_enabled=getattr(user, "auto_memory_enabled", True),
        default_voice=effective_voice,
        default_system_prompt=BASE_USER_PROMPT,
        prompt_presets=DEFAULT_PROMPT_PRESETS,
    )


@router.patch("/api/settings", response_model=UserSettingsResponse)
def update_user_settings(
    body: UpdateUserSettingsRequest,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
    settings: Settings = Depends(get_settings),
):
    """Update general system prompt, prompt caching, auto memory and default voice preferences."""
    with sessions() as db:
        db_user = db.scalar(select(User).where(User.id == user.id))
        if not db_user:
            raise HTTPException(404, "Utilisateur introuvable")

        if body.system_prompt is not None:
            db_user.system_prompt = body.system_prompt.strip()
        if body.prompt_cache_enabled is not None:
            db_user.prompt_cache_enabled = bool(body.prompt_cache_enabled)
        if body.auto_memory_enabled is not None:
            db_user.auto_memory_enabled = bool(body.auto_memory_enabled)
        if body.default_voice is not None:
            cleaned_voice = body.default_voice.strip()
            if not cleaned_voice:
                db_user.default_voice = None
            elif is_valid_voice_id(cleaned_voice):
                db_user.default_voice = cleaned_voice
            else:
                raise HTTPException(400, f"Voix par défaut inconnue : {cleaned_voice}")

        db.commit()
        db.refresh(db_user)

        user.system_prompt = db_user.system_prompt
        user.prompt_cache_enabled = db_user.prompt_cache_enabled
        user.auto_memory_enabled = db_user.auto_memory_enabled
        user.default_voice = db_user.default_voice

        effective_prompt = (db_user.system_prompt or "").strip() or BASE_USER_PROMPT
        effective_voice = resolve_voice_name(settings, db_user.default_voice)
        return UserSettingsResponse(
            system_prompt=effective_prompt,
            prompt_cache_enabled=db_user.prompt_cache_enabled,
            auto_memory_enabled=db_user.auto_memory_enabled,
            default_voice=effective_voice,
            default_system_prompt=BASE_USER_PROMPT,
            prompt_presets=DEFAULT_PROMPT_PRESETS,
        )


@router.get("/api/settings/api-keys", response_model=AdminApiKeysResponse)
def get_admin_api_keys(
    request: Request,
    _admin: User = Depends(require_admin),
    sessions: sessionmaker = Depends(get_sessions),
    settings: Settings = Depends(get_settings),
):
    """Retourne uniquement les métadonnées d'origine des 8 clés externes (zéro caractère exposé)."""
    vault = _get_vault(request, sessions, settings)
    return _build_admin_api_keys_response(settings, vault)


@router.patch("/api/settings/api-keys", response_model=AdminApiKeysResponse)
def update_admin_api_keys(
    body: UpdateAdminApiKeysRequest,
    request: Request,
    admin: User = Depends(require_admin),
    sessions: sessionmaker = Depends(get_sessions),
    settings: Settings = Depends(get_settings),
):
    """Enregistre et/ou réinitialise des surcharges de clés API après vérification Sudo du mot de passe Admin."""
    if not body.keys and not body.clear_keys:
        raise HTTPException(400, "Aucune modification de clé API fournie.")
    if len(body.keys) > 8:
        raise HTTPException(400, "Trop de clés fournies dans une seule requête.")

    try:
        normalized_updates = {validate_vault_key_name(k): v for k, v in body.keys.items()}
        normalized_clears = [validate_vault_key_name(k) for k in body.clear_keys]
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    overlap = set(normalized_updates) & set(normalized_clears)
    if overlap:
        raise HTTPException(400, "Une même clé ne peut pas être simultanément enregistrée et réinitialisée.")

    _verify_admin_sudo(request, sessions, admin, body.current_password)
    vault = _get_vault(request, sessions, settings)

    try:
        if normalized_updates:
            vault.upsert_overrides(normalized_updates, updated_by_user_id=admin.id)
        for clear_name in normalized_clears:
            vault.delete_override(clear_name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except VaultConfigurationError as exc:
        raise HTTPException(500, str(exc)) from exc

    settings._sync_vault_overrides(force_reload=True)
    return _build_admin_api_keys_response(settings, vault)


@router.post("/api/settings/api-keys/test", response_model=TestAdminApiKeyResponse)
async def test_admin_api_key(
    body: TestAdminApiKeyRequest,
    _admin: User = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """Exécute une sonde légère (timeout 5 s, $0) sur une clé candidate ou active sans l'exposer."""
    try:
        norm_name = validate_vault_key_name(body.key_name)
        valid, detail = await probe_provider_api_key(
            settings=settings,
            key_name=norm_name,
            candidate_value=body.candidate_value,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return TestAdminApiKeyResponse(key_name=norm_name, valid=valid, detail=detail)
