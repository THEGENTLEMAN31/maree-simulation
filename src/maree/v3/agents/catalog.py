"""agents.catalog — le catalogue de modèles et la résolution provider.

Séparé des adaptateurs : le catalogue ne connaît que ``ModelSpec`` et le
registre des fournisseurs (`ChatModelPort`). Le *câblage* (quelle instance
pour quel provider) se fait dans ``bootstrap`` — les tests n'enregistrent
que ce dont ils ont besoin (un stub), ce qui prouve l'interchangeabilité.
"""

from __future__ import annotations

from maree.v3.core.ports import ChatModelPort, ModelSpec

#: Résolution : alias -> spec. Deux tailles de décision (axe « la taille
#: compte-t-elle ? ») + une tête d'embedding (RAG). Le provider ``llamacpp``
#: est l'hôte natif projet (port 8081) ; ``stub`` sert aux tests.
CATALOG: dict[str, ModelSpec] = {
    "stub": ModelSpec("stub", "stub", "stub-bot", max_tokens=64),
    "petit": ModelSpec("petit", "llamacpp", "qwen3-0-6b", max_tokens=64, tags=("small",)),
    "decision": ModelSpec(
        "decision", "llamacpp", "gemma4-e2b", max_tokens=200, tags=("big", "decision")
    ),
    "embed": ModelSpec("embed", "llamacpp", "bge-m3", max_tokens=8, tags=("embed",)),
}

#: Registre des fournisseurs (adaptateurs concrets), rempli au bootstrap.
#: Un fournisseur absent = erreur claire à la résolution, pas un échec muet.
_PROVIDERS: dict[str, ChatModelPort] = {}


def register_provider(name: str, port: ChatModelPort) -> None:
    # idempotent : le bootstrap et les tests peuvent re-câbler sans conflit.
    _PROVIDERS[name] = port


def provider(name: str) -> ChatModelPort:
    try:
        return _PROVIDERS[name]
    except KeyError:
        raise KeyError(
            f"fournisseur inconnu : {name!r} (enregistrés : {sorted(_PROVIDERS)})"
        ) from None


def resolve_model(alias: str) -> ModelSpec:
    try:
        return CATALOG[alias]
    except KeyError:
        raise KeyError(
            f"alias de modèle inconnu : {alias!r} (catalogue : {sorted(CATALOG)})"
        ) from None


def chat_for(alias: str) -> tuple[ChatModelPort, ModelSpec]:
    """Retourne (adaptateur, spec) pour un alias — c'est l'entrée typique."""
    spec = resolve_model(alias)
    return provider(spec.provider), spec


__all__ = [
    "CATALOG",
    "chat_for",
    "provider",
    "register_provider",
    "resolve_model",
]