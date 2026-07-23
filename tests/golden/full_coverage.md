---
title: "Rapport d'essais du banc de mesure — Fixture couverture totale"
authors:
  - "Équipe CND"
  - "M. Durand"
date: 2026-07-15
keywords:
  - "banc de mesure"
  - "couverture"
  - "fixture"
  - "citations"
  - "figures"
description: "Manifest de référence exerçant chaque type de nœud et chaque variante du format CND 0.2.0 : familles de liens, pools, figures imbriquées, tables fusionnées."
lang: "fr"
cnd_version: "0.3.0"
built_at: "2026-07-15T08:30:00+00:00"
---

# Vue d'ensemble

Les mesures nominales sont récapitulées dans la table des mesures ; la structure atomique est illustrée plus bas.
[@durand2025, p. 42] [^fn-unit] [tab-mesures] @durand2025 [fig-atom]

1. Étalonner les capteurs
  1. Vérifier le zéro
  2. Vérifier la pleine échelle
2. Lancer l'acquisition

- Alimentation 24 V redondée
- Bus de terrain isolé galvaniquement

**Banc**
: Ensemble mécanique portant les capteurs sous test.
**Cycle**
: Séquence complète de montée et descente en charge.
**Dérive**
: Écart de mesure observé entre deux étalonnages.

Mesurer, c'est comparer à une référence.
— Manuel de métrologie interne

```python
def moyenne(valeurs):
    return sum(valeurs) / len(valeurs)
```

e(t) = m(t) - r(t)

## Résultats et figures
[fig-schema]

| Capteur | Nominal |
| --- | --- |
| PT-01 | 10 bar |
| FT-02 | 250 L/min |

*Table 1: Mesures nominales par capteur.*

| Zone | Relevés bruts |  |
| --- | --- | --- |
|  | 12.4 | 12.6 |

![Vue d'ensemble du banc de mesure](figures/banc.png)

*Figure 1: Schéma du banc de mesure.*

```json
{
  "frequence_hz": 10,
  "duree_s": 300
}
```

*Listing 1: Configuration de l'acquisition.*

![Courbe avant étalonnage](figures/avant.png)

*(a) Avant étalonnage.*

![Courbe après étalonnage](figures/apres.png)

*(b) Après étalonnage.*

*Figure 2: Comparaison avant/après étalonnage.*

![Maille cristalline](figures/reseau.svg)

*Atome 1: Structure atomique du réseau mesuré.*

[[figure:00000000-0000-4000-e000-000000000025 kind="canvas" number="3" caption="Tracé vectoriel non convertible."]]

![Logo du banc, image nue hors figure](figures/logo-banc.png)

[[image:00000000-0000-4000-e000-000000000027 alt="Image incorporée sans chemin extrait"]]

# Références

Grille brute en annexe. Les travaux antérieurs couvrent la méthode, l'auteur, l'année et une citation muette.
[grid-layout] [^fn-proto] [@nguyen2023] @durand2025 @nguyen2023

## Footnotes

[^fn-unit]: Toutes les valeurs sont exprimées en unités SI.
[^fn-proto]: Le prototype de la grille figure au dossier d'essais 2026-041.

## Bibliography

- **durand2025** — Durand, M., & Petit, C. (2025). Étalonnage automatique des chaînes de mesure. Revue de Métrologie Appliquée, 8(2), 101–118.
- **nguyen2023** — Nguyen, T. (2023). Field bus diagnostics in practice. Munich: Feldbus Verlag.
