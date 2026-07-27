---
title: "Manuel d'exploitation DCS — Fixture intégration CND"
authors:
  - "Équipe CND"
  - "L. Faure"
date: 2026-06-06
keywords:
  - "DCS"
  - "chunking"
  - "cross-refs"
  - "tables"
  - "fixture"
description: "Manifest de référence couvrant les cas limites du chunker : contenu pré-heading, imbrication profonde, refs intra/inter-chunks, tables complexes."
lang: "fr"
cnd_version: "0.3.0"
built_at: "2026-06-06T12:00:00+00:00"
---

Résumé exécutif placé avant le premier titre. Ce paragraphe doit produire un chunk isolé avec un heading_path vide.

# Architecture générale

Le système DCS repose sur trois couches fonctionnelles : acquisition, traitement et supervision.

## Couche d'acquisition
[tab-plages-mesure]

Les capteurs analogiques et numériques sont regroupés par bus de terrain. Voir le tableau des plages de mesure.
[tab-plages-mesure]

La fréquence d'échantillonnage nominale est de 10 Hz pour les boucles rapides.

| Capteur |  | Plage |
| --- | --- | --- |
| Pression | PT-101 | 0–16 bar |
|  | PT-102 | 0–25 bar |
| Débit | FT-201 | 0–500 L/min |

*Table 1: Plages de mesure des capteurs de terrain.*

## Couche de traitement
[tab-plages-mesure] [tab-recap-signaux]

Les algorithmes de régulation s'exécutent sur le contrôleur redondant. Les plages capteurs (Table 1) et le récapitulatif annexe (Table 4) doivent rester cohérents.
[tab-plages-mesure] [tab-recap-signaux]

| Boucle | Mode | Kp |
| --- | --- | --- |
| LC-101 | AUTO | 1.25 |
| FC-202 | CASCADE | 0.80 |

*Table 2: Boucles de régulation PID actives.*

# Exploitation

## Surveillance opérateur

### Gestion des alarmes
[tab-delais-alarmes]

Les alarmes sont classées en quatre niveaux de criticité : info, avertissement, alarme, critique.

Le délai d'acquittement maximal est défini par la politique site. Consulter la matrice des délais.
[tab-delais-alarmes]

| Niveau |  | Délai max |
| --- | --- | --- |
| Info | — | 24 h |
| Critique | P1 | 5 min |

*Table 3: Délais d'acquittement par niveau de criticité.*

## Maintenance préventive

Les interventions planifiées suivent le calendrier OEM. Aucune table n'est associée à cette section.

# Annexes

| Tag | Unité | Bus |
| --- | --- | --- |
| PT-101 | bar | Profibus |
| FT-201 | L/min | Modbus |

*Table 4: Récapitulatif des signaux instrumentés.*
