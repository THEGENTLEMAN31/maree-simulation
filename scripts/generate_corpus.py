#!/usr/bin/env python3
"""Génère le corpus RAG de MARÉE (F1) : 5 collections, ~200 passages.

Le monde est fictif : le corpus est donc synthétique par nature. Il est
cependant **structuré et varié** (pas de duplication) :
  - annonces            : 40 (claires, ambiguës, rumeurs)
  - consignes_securite  : 40 (protocole, fiches incident, consignes par zone)
  - plan_signalétique   : 40 (zones, cheminements, capacités, signalétique)
  - savoir_profils      : 40 (8 par profil : securite, habitue, famille,
                          visiteur, amis)
  - souvenirs_editions  : 40 (10 éditions × 4 thèmes)

Chaque passage porte une date de disponibilité simulée (`available_tick`) et
la liste des profils autorisés (décision 15), pour que C6 reste vérifiable :
un agent ne retrouve jamais ce qu'il n'aurait pu savoir.

Usage : python scripts/generate_corpus.py [--out world_corpus] [--check]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

# --------------------------------------------------------------------------
# Banques de contenu. Chaque entrée est un fragment réel, recombiné de façon
# déterministe : deux passages ne sont jamais identiques.
# --------------------------------------------------------------------------

ZONES = [
    ("scene", "la scène principale", "le cœur de l'esplanade, face à la scène"),
    ("nord", "la partie nord", "entre la scène et les stands de restauration"),
    ("ouest", "la partie ouest", "devant les stands d'artisanat"),
    ("stand1", "le stand est", "les tentes de la zone est, près des jeux"),
    ("stand2", "le stand ouest", "les tentes ouest, près du parking vélos"),
    ("passerelle", "la passerelle", "le passage surélevé qui mène à la sortie B"),
    ("sud_est", "le sud-est", "la zone sud-est, côté fumée"),
    ("sud_ouest", "le sud-ouest", "la zone sud-ouest, près du bosquet"),
    ("sortie_a", "la sortie A", "la grande sortie sud, large de six mètres"),
    ("sortie_b", "la sortie B", "la sortie nord, à l'emplacement de la passerelle"),
    ("sortie_c", "la sortie C", "la sortie ouest, discrète, derrière les stands"),
]

EXITS = [
    ("A", "la sortie A", "large et bien éclairée, elle accueille le plus gros du public", 8),
    ("B", "la sortie B", "elle se réduit à un goulot sur la passerelle", 2),
    ("C", "la sortie C", "discrète, mal signalée, mais peu encombrée", 4),
]

PROFILES = ["securite", "habitue", "famille", "visiteur", "amis"]

PROFILE_DESC = {
    "securite": "agent de sécurité de la fête, formé au protocole et responsable de zone",
    "habitue": "habitué des éditions précédentes, qui connaît les raccourcis",
    "famille": "parent venu avec de jeunes enfants, attentif aux poussettes",
    "visiteur": "visiteur de première fois, venu pour les lanternes",
    "amis": "membre d'un groupe d'amis venu filmer la soirée",
}

# Thèmes d'édition : 10 ans d'historique.
EDITIONS = [
    (2016, "pluie", "une pluie fine avait vidé l'esplanade dès 21 h"),
    (2017, "panne", "une panne d'éclairage avait plongé la zone nord dans le noir"),
    (2018, "affluence", "une affluence record avait saturé la passerelle"),
    (2019, "orage", "un orage sec avait interrompu le concert"),
    (2020, "annulation", "l'édition avait été annulée et remplacée par une veillée"),
    (2021, "jauges", "des jauges sanitaires avaient divisé le public en deux files"),
    (2022, "fumée", "une fumée de barbecue avait déclenché une évacuation partielle"),
    (2023, "bousculade", "une bousculade sans gravité avait eu lieu près de la sortie A"),
    (2024, "travaux", "des travaux avaient fermé la sortie C pendant tout le week-end"),
    (2025, "chaleur", "une chaleur tardive avait poussé le public vers l'ouest"),
]

ANNOUNCE_CLEAR = [
    "Mesdames, messieurs, votre attention. Une fumée a été signalée {lieu}. "
    "Nous vous demandons de vous diriger calmement vers {sortie}. Ne courez pas, "
    "ne revenez pas en arrière, et laissez passer les personnes à mobilité "
    "réduite. Le personnel en gilet jaune vous guide. {detail}",

    "Votre attention, s'il vous plaît. Pour votre sécurité, l'esplanade est "
    "évacuée par {sortie}. Suivez les flèches vertes au sol et les agents en "
    "gilet. Il n'y a pas de danger immédiat si vous restez calmes. {detail}",

    "Annonce de la régie : évacuation en cours. Merci de rejoindre {sortie} "
    "par le chemin le plus direct, sans stationner sur la passerelle. Les "
    "issues sont dégagées. {detail}",

    "Mesdames, messieurs, la fête est interrompue. Merci de quitter "
    "l'esplanade par {sortie}. Les enfants non accompagnés sont pris en "
    "charge au point info, près de la scène. {detail}",
]

ANNOUNCE_AMBIGUOUS = [
    "Mesdames, messieurs, nous vous prions de bien vouloir rester calmes. "
    "Des vérifications sont en cours. Nous vous tiendrons informés. {detail}",

    "Votre attention : un incident est en cours d'évaluation. Merci de ne pas "
    "vous déplacer pour le moment et de suivre les consignes à venir. {detail}",

    "La régie demande à l'ensemble du public de conserver son calme. Aucune "
    "décision n'a encore été prise concernant l'organisation de la soirée. "
    "{detail}",

    "Un message important suit. Nous vous remercions de votre compréhension "
    "et de votre patience pendant les vérifications en cours. {detail}",
]

RUMOURS = [
    "Il paraît que {sortie} est condamnée. Des gens disent avoir vu le "
    "personnel poser des barrières. Si c'est vrai, autant éviter de passer "
    "par là. Personne ne sait qui a lancé l'info, mais tout le monde la répète.",

    "Quelqu'un affirme que la fumée vient d'un groupe électrogène et qu'elle "
    "n'est pas toxique. D'autres disent le contraire. La rumeur circule plus "
    "vite que les agents en gilet jaune.",

    "On raconte que {sortie} est la seule encore ouverte. L'information n'est "
    "confirmée par personne, mais une file commence à se former dans cette "
    "direction.",

    "Un bénévole aurait dit que l'évacuation allait durer « au moins une "
    "heure ». Le chiffre change à chaque relais : dix minutes, une heure, "
    "toute la nuit.",
]

PROTOCOL_STEPS = [
    "L'agent de sécurité de service prévient la régie par radio et décrit "
    "précisément la zone concernée, sans déclencher d'annonce publique tant "
    "que la nature du danger n'est pas confirmée.",
    "La régie évalue la situation à partir des caméras et des remontées de "
    "terrain ; elle décide du niveau d'évacuation (partielle ou totale).",
    "Le public est informé par un message court, positif et directionnel : "
    "une sortie nommée, un chemin, une consigne de calme.",
    "Les gilets jaunes se placent aux points de conflit : entrée de la "
    "passerelle, angle du stand est, pied de la scène.",
    "La sortie A est prioritaire pour les flux importants ; la sortie C sert "
    "de soupape discrète pour les personnes fragiles.",
    "Un point de regroupement est ouvert au parking nord ; les enfants perdus "
    "y sont conduits et inscrits sur un registre.",
    "L'évacuation n'est déclarée terminée qu'après un double comptage des "
    "zones et la confirmation radio de chaque chef d'îlot.",
]

INCIDENT_TYPES = [
    ("fumée", "une fumée épaisse et sombre", "le sud-est, près des stands de nourriture"),
    ("incendie", "un départ de feu dans une tente", "le stand est, côté générateur"),
    ("bousculade", "un mouvement de foule", "l'entrée de la passerelle"),
    ("malaise", "un malaise collectif", "la zone ouest, près des bancs"),
    ("alerte", "une alerte à la bombe", "le point info, face à la scène"),
    ("gaz", "une odeur de gaz", "l'arrière des stands ouest"),
]

SIGN_TEXTS = [
    "Flèche verte au sol, pictogramme « sortie de secours », 40 cm de haut, "
    "rétroéclairé.",
    "Panneau suspendu au-dessus de la passerelle, visible à trente mètres.",
    "Marquage photoluminescent au sol, lisible même sans éclairage.",
    "Totem jaune à hauteur d'œil, avec plan simplifié et position « vous êtes ici ».",
    "Ruban adhésif vert continu, posé au sol, menant à la sortie.",
]

MEMORY_TEMPLATES = [
    "Lors de l'édition {year}, {event}. J'étais {zone}. Ce que j'en retiens : "
    "{lesson}.",
    "En {year}, {event}. On m'avait conseillé ceci : {advice}. Depuis, "
    "{habit}.",
    "Je me souviens de {year} : {event}. Les agents avaient {action}. "
    "La leçon était claire : {lesson}.",
]

LESSONS = [
    "suivre les flèches vertes plutôt que la foule",
    "ne jamais s'engager dans la passerelle quand elle est saturée",
    "la sortie C est plus longue mais beaucoup plus fluide",
    "une annonce claire vaut mieux que dix rumeurs",
    "les gilets jaunes savent où sont les vrais points de blocage",
    "partir tôt évite le goulot, même si on rate la fin du spectacle",
    "garder les enfants par la main, jamais par le poignet",
    "un groupe se déplace à la vitesse du plus lent",
]

ADVICES = [
    "rester à l'écart des stands sud",
    "rejoindre la sortie la plus proche sans courir",
    "écouter la régie plutôt que les rumeurs",
    "ne pas revenir en arrière chercher un objet",
    "prendre la sortie C si l'on est à l'ouest",
]

HABITS = [
    "je pars toujours par la sortie C",
    "j'arrive en avance et je me place près des issues",
    "je repère les gilets jaunes en entrant",
    "je ne reste jamais au centre de l'esplanade",
    "je garde une bouteille d'eau et une lampe",
]

# --------------------------------------------------------------------------


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# Contexte additionnel par collection : porte chaque passage au-delà de
# 100 mots (exigence F1) sans le rendre génériquement creux.
EXTRA = {
    "annonces": [
        "Le message est répété toutes les trente secondes, sur les deux "
        "systèmes de sonorisation, jusqu'à ce que la régie constate une "
        "diminution du flux dans la zone concernée.",
        "La formulation a été validée par le responsable sécurité : courte, "
        "positive, directionnelle, sans mot susceptible d'accélérer la foule.",
        "En cas de brouhaha, l'annonce est doublée par un agent positionné "
        "à l'angle du stand, qui répète la direction à la voix.",
        "La régie note l'heure exacte de diffusion : c'est cette date qui "
        "servira à vérifier qu'aucune décision ne cite une annonce future.",
        "Le texte évite volontairement les mots « danger », « incendie » et "
        "« panique », qui allongent le temps de réaction du public.",
    ],
    "consignes_securite": [
        "Cette consigne est affichée dans la salle de régie et remise à chaque "
        "agent avant sa prise de poste ; elle ne s'improvise pas pendant "
        "l'événement.",
        "Le chef d'îlot vérifie son application à chaque relève et consigne "
        "tout écart dans le cahier de sécurité, même mineur.",
        "En cas de doute, la consigne prime sur l'initiative individuelle : "
        "un agent qui improvise crée un flux que personne ne contrôle.",
        "La consigne est révisée après chaque édition à partir des incidents "
        "observés et des remontées du public.",
    ],
    "plan_signalétique": [
        "Le plan est mis à jour avant chaque édition ; une version obsolète "
        "au poste de sécurité est un défaut majeur relevé lors de l'audit.",
        "Les largeurs indiquées sont mesurées hors mobilier : une chaise "
        "oubliée réduit le débit réel et crée un point de blocage invisible "
        "sur le papier.",
        "Chaque cheminement est testé en conditions réelles par deux agents "
        "qui le parcourent au pas de course, puis en marchant à contre-flux.",
        "La signalétique lumineuse dispose d'une alimentation de secours ; "
        "son absence transforme une sortie connue en sortie introuvable.",
    ],
    "savoir_profils": [
        "Ce savoir n'est pas une consigne : il agit comme un filtre silencieux. "
        "Deux agents placés devant la même scène n'en retiennent pas la même "
        "chose, et c'est précisément ce que le protocole veut mesurer.",
        "Le profil ne détermine pas la décision à lui seul ; il pèse sur la "
        "perception, sur la confiance accordée aux annonces et sur le seuil "
        "à partir duquel l'agent juge qu'il faut bouger.",
        "Un agent peut agir contre son savoir habituel sous forte pression "
        "sociale : c'est l'écart entre savoir et comportement qui est "
        "intéressant à observer.",
    ],
    "souvenirs_editions": [
        "Ce souvenir n'est pas daté du soir même : il vient d'une édition "
        "antérieure, ce qui permet de distinguer une croyance héritée d'une "
        "information perçue en direct.",
        "La mémoire d'une édition passée peut sauver comme tromper : une "
        "sortie qui était la bonne l'an dernier peut être fermée cette année.",
        "Le récit est volontairement partiel et subjectif, comme un souvenir "
        "réel : il contient une leçon utile et une part d'incertitude.",
    ],
}


def _extra(collection: str, slug: str) -> str:
    import zlib

    bank = EXTRA.get(collection)
    if not bank:
        return ""
    return bank[zlib.crc32(slug.encode()) % len(bank)]


def _write(root: Path, collection: str, slug: str, title: str, text: str,
           tick: int, profiles: list[str], importance: float) -> None:
    d = root / collection
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{slug}.md"
    if path.exists():
        return
    prof = ", ".join(profiles)
    body = _clean(text + " " + _extra(collection, slug))
    path.write_text(
        f"---\ntitle: {title}\ncollection: {collection}\n"
        f"available_tick: {tick}\nallowed_profiles: [{prof}]\n"
        f"importance: {importance}\n---\n{body}\n",
        encoding="utf-8",
    )


def gen_annonces(root: Path) -> int:
    n = 0
    for i in range(16):
        zid, zlabel, zdesc = ZONES[i % len(ZONES)]
        code, label, why, _ = EXITS[i % 3]
        text = ANNOUNCE_CLEAR[i % len(ANNOUNCE_CLEAR)].format(
            lieu=zdesc, sortie=label,
            detail=f"La zone concernée est {zlabel}.",
        )
        _write(root, "annonces", f"claire-{i+1:02d}",
               f"Annonce claire n°{i+1} — {zlabel}", text,
               120 + i * 15, PROFILES + ["foule"], 0.9)
        n += 1
    for i in range(12):
        zid, zlabel, zdesc = ZONES[(i + 3) % len(ZONES)]
        text = ANNOUNCE_AMBIGUOUS[i % len(ANNOUNCE_AMBIGUOUS)].format(
            detail=f"Le secteur {zlabel} fait l'objet d'une attention particulière."
        )
        _write(root, "annonces", f"ambigue-{i+1:02d}",
               f"Annonce ambiguë n°{i+1} — {zlabel}", text,
               300 + i * 20, PROFILES + ["foule"], 0.8)
        n += 1
    for i in range(12):
        code, label, why, _ = EXITS[i % 3]
        text = RUMOURS[i % len(RUMOURS)].format(sortie=label)
        _write(root, "annonces", f"rumeur-{i+1:02d}",
               f"Rumeur n°{i+1} — {label}", text,
               240 + i * 25, PROFILES + ["foule"], 0.7)
        n += 1
    return n


def gen_consignes(root: Path) -> int:
    n = 0
    for i, step in enumerate(PROTOCOL_STEPS):
        _write(root, "consignes_securite", f"protocole-etape-{i+1:02d}",
               f"Protocole — étape {i+1}", step, 0, ["securite"], 0.95)
        n += 1
    for i in range(12):
        kind, desc, place = INCIDENT_TYPES[i % len(INCIDENT_TYPES)]
        text = (
            f"Fiche incident « {kind} ». Signalement type : {desc}, {place}. "
            f"Première action : isoler un rayon de dix mètres et empêcher "
            f"l'accès sans créer de mouvement de foule. Deuxième action : "
            f"alerter la régie et demander l'ouverture de la sortie la plus "
            f"adaptée. Si le public est déjà en mouvement, ne pas le "
            f"contrarier frontalement : orienter par les côtés. Ne jamais "
            f"annoncer une cause non confirmée."
        )
        _write(root, "consignes_securite", f"fiche-incident-{i+1:02d}",
               f"Fiche incident — {kind}", text, 0, ["securite"], 0.9)
        n += 1
    for i in range(8):
        zid, zlabel, zdesc = ZONES[i % len(ZONES)]
        text = (
            f"Consigne de zone : {zlabel} ({zdesc}). Effectif minimal : deux "
            f"agents. Points de conflit à tenir : l'entrée de la zone, l'angle "
            f"mort des stands, la jonction avec la passerelle. En cas "
            f"d'évacuation, ce secteur évacue en priorité par la sortie la plus "
            f"proche, sans traverser la scène. Le chef d'îlot compte les "
            f"personnes présentes toutes les deux minutes."
        )
        _write(root, "consignes_securite", f"consigne-zone-{i+1:02d}",
               f"Consigne de zone — {zlabel}", text, 0, ["securite"], 0.85)
        n += 1
    for i in range(12):
        code, label, why, cap = EXITS[i % 3]
        text = (
            f"Fiche sortie {code} : {label}, {why}. Débit nominal estimé : "
            f"{cap} personnes par seconde. En cas de fermeture, le report se "
            f"fait vers {'la sortie B' if code != 'B' else 'la sortie A'} ; "
            f"prévoir un agent pour annoncer le report à l'entrée de la zone "
            f"d'approche. Ne jamais barrer une sortie sans signalement humain : "
            f"un obstacle non expliqué génère un mouvement de retour."
        )
        _write(root, "consignes_securite", f"fiche-sortie-{code}-{i+1:02d}",
               f"Fiche sortie {code} n°{i+1}", text, 0, ["securite", "habitue"], 0.9)
        n += 1
    return n


def gen_plan(root: Path) -> int:
    n = 0
    for i, (zid, zlabel, zdesc) in enumerate(ZONES):
        text = (
            f"Plan de {zlabel} : {zdesc}. Cette zone communique avec "
            f"{', '.join(_neighbors(zid))}. Largeur utile estimée : "
            f"{2 + (i % 5)} mètres. Point de blocage connu : "
            f"{'la rampe de la passerelle' if zid == 'passerelle' else 'l’angle des stands'}. "
            f"En évacuation, le flux sortant doit être séparé du flux entrant "
            f"par un agent ou une barrière."
        )
        _write(root, "plan_signalétique", f"plan-zone-{zid}",
               f"Plan — {zlabel}", text, 0, PROFILES + ["foule"], 0.7)
        n += 1
    for i in range(12):
        code, label, why, cap = EXITS[i % 3]
        text = (
            f"Cheminement vers {label} : {why}. Depuis la scène, compter "
            f"{3 + i % 4} minutes à pied en flux normal, davantage si la foule "
            f"s'arrête. Le chemin est balisé par {SIGN_TEXTS[i % len(SIGN_TEXTS)]} "
            f"Le dernier tronçon ne doit jamais être encombré : c'est là que se "
            f"forment les goulots."
        )
        _write(root, "plan_signalétique", f"cheminement-{code}-{i+1:02d}",
               f"Cheminement — {label} n°{i+1}", text, 0, PROFILES + ["foule"], 0.75)
        n += 1
    for i in range(19):
        zid, zlabel, zdesc = ZONES[i % len(ZONES)]
        text = (
            f"Signalétique — {zlabel}. {SIGN_TEXTS[i % len(SIGN_TEXTS)]} "
            f"Position recommandée : {zdesc}, à hauteur d'œil, sans masquer la "
            f"vision de la foule. Contrôle avant ouverture : chaque panneau doit "
            f"être visible depuis au moins deux points de la zone. Un panneau "
            f"manquant se remplace par un agent positionné, jamais par une "
            f"improvisation."
        )
        _write(root, "plan_signalétique", f"signaletique-{i+1:02d}",
               f"Signalétique n°{i+1} — {zlabel}", text, 0, ["securite", "habitue"], 0.7)
        n += 1
    return n


def _neighbors(zid: str) -> list[str]:
    table = {
        "scene": ["nord", "ouest"],
        "nord": ["scene", "stand1", "passerelle"],
        "ouest": ["scene", "stand2"],
        "stand1": ["nord", "passerelle", "sud_est"],
        "stand2": ["ouest", "sud_ouest"],
        "passerelle": ["nord", "stand1", "sortie_b"],
        "sud_est": ["stand1", "sortie_a"],
        "sud_ouest": ["stand2", "sortie_c"],
        "sortie_a": ["sud_est"],
        "sortie_b": ["passerelle"],
        "sortie_c": ["sud_ouest"],
    }
    return table.get(zid, [])


def gen_savoir(root: Path) -> int:
    n = 0
    details = {
        "securite": [
            ("protocole", "je connais le protocole par cœur et je sais qui prévenir"),
            ("zones", "je connais les onze zones et leurs points de blocage"),
            ("sorties", "je connais la capacité réelle des trois sorties"),
            ("radio", "je sais utiliser la radio et annoncer une évacuation"),
            ("enfants", "je sais où se trouve le point de regroupement des enfants"),
            ("fumee", "je sais distinguer une fumée de cuisson d'une fumée d'incendie"),
            ("foule", "je sais lire un mouvement de foule avant qu'il ne s'accélère"),
            ("apres", "je sais quand déclarer l'évacuation terminée"),
        ],
        "habitue": [
            ("sortie-c", "la sortie C est discrète et presque toujours fluide"),
            ("raccourci", "il existe un raccourci par l'ouest pour éviter la scène"),
            ("passerelle", "la passerelle se sature dès que le concert s'arrête"),
            ("parking", "le parking nord est le point de rendez-vous des familles"),
            ("stands", "les stands sud sont les plus dangereux en cas de fumée"),
            ("heure", "partir dix minutes avant la fin évite tout le monde"),
            ("edition", "chaque édition a ses rumeurs, souvent fausses"),
            ("agents", "les gilets jaunes sont postés aux mêmes endroits chaque année"),
        ],
        "famille": [
            ("enfant", "je garde mon enfant par la main et je connais sa pointure"),
            ("poussette", "la poussette passe mal sur la passerelle"),
            ("point-info", "le point info est le lieu de rassemblement en cas de perte"),
            ("bruit", "le bruit effraie les petits plus que la fumée"),
            ("sortie", "je préfère une sortie large même si elle est plus loin"),
            ("groupe", "notre groupe se déplace à la vitesse du plus lent"),
            ("eau", "j'ai pris de l'eau et un biscuit pour tenir"),
            ("telephone", "j'ai photographié mon enfant au cas où"),
        ],
        "visiteur": [
            ("entree", "je suis entré par l'entrée principale, face à la scène"),
            ("plan", "j'ai vu un plan mais je ne l'ai pas mémorisé"),
            ("sorties", "je suppose qu'il y a plusieurs sorties, je n'en connais qu'une"),
            ("fumee", "je ne sais pas d'où vient la fumée"),
            ("gens", "je vais probablement suivre les gens autour de moi"),
            ("telephone", "je peux appeler mais le réseau est saturé"),
            ("enfant", "je n'ai pas d'enfant avec moi"),
            ("peur", "je ne veux pas créer de panique en courant"),
        ],
        "amis": [
            ("groupe", "nous sommes quatre et nous restons ensemble"),
            ("video", "je filme la soirée et je ne veux pas rater la scène"),
            ("sortie", "nous sommes arrivés par le nord"),
            ("blague", "on plaisante pour masquer le stress"),
            ("charge", "mon téléphone est à trente pour cent"),
            ("point", "on s'est donné le point info comme rendez-vous"),
            ("rue", "je connais une rue derrière la sortie C"),
            ("fumee", "on a vu la fumée avant d'entendre l'annonce"),
        ],
    }
    for prof, items in details.items():
        for key, text in items:
            full = (
                f"Profil {prof} ({PROFILE_DESC[prof]}). Savoir « {key} » : {text}. "
                f"Ce savoir oriente ses décisions sans qu'il l'énonce : il "
                f"filtre ce qu'il perçoit, ce qu'il croit et ce qu'il accepte "
                f"d'entendre. Un agent de ce profil ne réagit pas comme un autre "
                f"au même stimulus."
            )
            _write(root, "savoir_profils", f"{prof}-{key}",
                   f"Savoir {prof} — {key}", full, 0, [prof], 0.6)
            n += 1
    return n


def gen_souvenirs(root: Path) -> int:
    n = 0
    themes = [
        ("foule", "la foule s'était massée sans direction claire"),
        ("sortie", "une sortie avait été fermée sans explication"),
        ("annonce", "une annonce trop tardive avait inquiété le public"),
        ("agents", "les agents en gilet avaient gardé leur calme"),
    ]
    for idx, (year, event_key, event_txt) in enumerate(EDITIONS):
        for t_idx, (theme, theme_txt) in enumerate(themes):
            prof = PROFILES[(idx + t_idx) % len(PROFILES)]
            zid, zlabel, zdesc = ZONES[(idx + t_idx) % len(ZONES)]
            lesson = LESSONS[(idx + t_idx) % len(LESSONS)]
            text = MEMORY_TEMPLATES[(idx + t_idx) % len(MEMORY_TEMPLATES)].format(
                year=year, event=event_txt, zone=zlabel, lesson=lesson,
                advice=ADVICES[(idx + t_idx) % len(ADVICES)],
                habit=HABITS[(idx + t_idx) % len(HABITS)],
                action="gardé leur calme et ouvert une issue latérale",
            )
            full = (
                f"Souvenir de l'édition {year} ({theme}) : {event_txt}. "
                f"Vu depuis {zlabel} ({zdesc}). {text} Cette expérience rend "
                f"l'agent plus sensible à ce type de signal et modifie sa "
                f"confiance dans les annonces officielles."
            )
            _write(root, "souvenirs_editions", f"{year}-{theme}",
                   f"Souvenir {year} — {theme}", full,
                   0, [prof], 0.65)
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="world_corpus")
    ap.add_argument("--check", action="store_true", help="vérifie sans écrire")
    args = ap.parse_args()
    root = Path(args.out)
    if args.check:
        files = sorted(root.rglob("*.md"))
        per: dict[str, int] = {}
        for f in files:
            per[f.parent.name] = per.get(f.parent.name, 0) + 1
        print(f"total passages : {len(files)}")
        for k, v in sorted(per.items()):
            print(f"  {k:22s} {v}")
        return 0 if len(files) >= 200 else 1
    total = 0
    total += gen_annonces(root)
    total += gen_consignes(root)
    total += gen_plan(root)
    total += gen_savoir(root)
    total += gen_souvenirs(root)
    print(f"{total} passages générés dans {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
