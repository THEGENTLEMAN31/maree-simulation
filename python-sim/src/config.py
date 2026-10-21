"""Configuration de la simulation.

Décision 11 : aucun paramètre dans le code ; tout passe par un fichier
de configuration (YAML) chargé au lancement.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class ProfileSpec(BaseModel):
    """Définition d'un profil d'agent (décision 6 : interface uniforme)."""

    name: str
    count: int
    kind: Literal["llm", "rules"] = "llm"
    # Nom de modèle libre : "gemma4-e2b"/"gemma4-e4b" en prod (llama.cpp
    # router), ou un nom Ollama pour le test d'intégration local.
    model: str | None = None
    temperature: float = 0.3
    priority: str = ""
    knows_at_start: str = ""
    think_interval: int | None = None  # rythme propre (async, C4)

    def override(self, **kw: Any) -> "ProfileSpec":
        return self.model_copy(update=kw)


class WorldSpec(BaseModel):
    """Paramètres du monde (Port-Aubel, esplanade, 3 sorties)."""

    smoke_tick: int = 0
    smoke_spread_interval: int = 6
    evac_duration_ticks: int = 900  # 15 min simulées à 1 s / tick
    pre_days_ticks: int = 3 * 24 * 60  # 3 jours simulés (minutes)
    # Variantes expérimentales (protocole X1–X7) — optionnelles.
    announcement_tick: int | None = None
    announcement_clarity: Literal["clear", "ambiguous"] | None = None
    exits_closed: dict[str, int] = Field(default_factory=dict)  # code -> tick fermeture
    experiment_flags: dict[str, bool] = Field(default_factory=dict)
    # Pas de décision commun en mode synchrone (décision 10) : les agents
    # agissent tous ensemble, mais périodiquement, pas à chaque tick.
    decision_period_sync: int = 10


class CollectorSpec(BaseModel):
    """Collecteur de métriques (F2)."""

    sample_size: int = 30


class SimulationConfig(BaseModel):
    """Configuration racine de la simulation."""

    run_id: str = Field(default="run_demo", description="Identité du run (décision 5)")
    seed: int = 42
    mode: Literal["sync", "async"] = "sync"
    tick_duration_ms: int = 1000
    max_ticks: int = 100
    population: list[ProfileSpec] = Field(default_factory=list)
    world: WorldSpec = Field(default_factory=WorldSpec)
    log_dir: str = "/logs"
    collect: CollectorSpec = Field(default_factory=CollectorSpec)
    llm: dict[str, Any] = Field(
        default_factory=lambda: {"base_url": "http://llama-cpp:8081/v1"}
    )

    def config_hash(self) -> str:
        """Hash canonique de la configuration (décision 5 : identité de run).

        Ordre canonique par champ ; le hash identifie la configuration
        indépendamment du run_id (qui sert d'identité d'instance).
        """
        canonical = {
            "seed": self.seed,
            "mode": self.mode,
            "max_ticks": self.max_ticks,
            "world": self.world.model_dump(),
            "population": sorted(
                (p.model_dump() for p in self.population),
                key=lambda x: (x["name"], x.get("model")),
            ),
        }
        return hashlib.sha256(
            yaml.safe_dump(canonical, sort_keys=True).encode()
        ).hexdigest()[:16]


def load_config(path: str | Path) -> SimulationConfig:
    """Charge et valide une configuration YAML."""
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return SimulationConfig.model_validate(cfg)