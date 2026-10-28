"""Identifiants typés.

Des alias de type (PEP 695) plutôt que des chaînes nues : zéro coût à
l'exécution, mais le lecteur — et mypy — savent ce qu'une variable
représente. Un `AgentId` ne se confond pas avec un `ExitId`.
"""

type RunId = str
type AgentId = str
type ZoneId = str
type ExitId = str
type Tick = int
type Seq = int

#: Coordonnées en mètres, repère du plan (origine en bas à gauche).
type Point = tuple[float, float]
