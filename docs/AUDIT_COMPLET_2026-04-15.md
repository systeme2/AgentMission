# Audit complet — Mission Agent

_Date de l'audit : 15 avril 2026_

## Méthodologie

- Exécution de la suite de tests complète (`pytest -q`).
- Revue ciblée des points critiques : agrégation des sources, configuration active, dépendances runtime.
- Validation de correctifs rapides sur les causes racines les plus bloquantes.

## Résultat global

### Snapshot initial (avant correctifs)

- **762 tests collectés**
- **723 passés**
- **36 en échec**
- **3 ignorés**

### Snapshot après correctifs appliqués

- **763 tests collectés**
- **741 passés**
- **19 en échec**
- **3 ignorés**

➡️ **Gain net : 17 tests réparés**.

## Causes racines identifiées

### 1) Déduplication trop agressive dans le collector (impact majeur)

Le collector supprimait des missions valides (notamment en charge/concurrence) à cause d'une logique de dédup trop large sur les titres.
Effet observé: des batchs attendus à 20–60 missions redescendaient à 1 mission.

✅ Correctif appliqué:
- La dédup est désormais centrée sur l'URL (avec conservation d'un `title_hash` technique pour la DB), sans suppression fuzzy agressive.

### 2) Incompatibilité OpenAI lazy client / environnement (impact analyse IA)

Erreur observée dans les tests d'analyse IA:
`TypeError: Client.__init__() got an unexpected keyword argument 'proxies'`

✅ Correctifs appliqués:
- Ajout d'un garde-fou dans `agents/analyzer.py` pour éviter que le lazy proxy `openai.chat` casse les tests/mocks.
- Ajout d'un pin de compatibilité dans `requirements.txt`: `httpx<0.28`.

### 3) Divergence entre `SOURCE_MAP` et `SOURCES_ENABLED` (impact fonctionnel)

Constat:
- `SOURCE_MAP` contient 39 connecteurs.
- Plusieurs tests historiques attendent une baseline 23 sources + activations internationales par défaut.
- La configuration actuelle privilégie volontairement un scope FR (international désactivé par défaut).

Impact:
- Échecs de tests de non-régression alignés sur une ancienne baseline produit.

➡️ Action recommandée:
- Décider explicitement entre:
  1) baseline "produit FR" (actuelle), ou
  2) baseline "historique tests".
- Puis aligner les tests et la config sur cette décision.

### 4) Dépendance Playwright absente (impact scraping JS)

Plusieurs tests liés à Malt échouent avec:
`ModuleNotFoundError: No module named 'playwright'`

➡️ Action recommandée:
- Installer Playwright en CI (et chromium), ou
- marquer les tests Malt comme conditionnels si la dépendance n'est pas disponible.

## Plan d'action priorisé

1. **P0 (fait)**: corriger la dédup collector qui supprimait des jobs légitimes.
   - amélioration supplémentaire: les jobs sans URL sont maintenant conservés via une clé de déduplication de fallback (empreinte source+titre+description).
2. **P0 (fait)**: durcir la compatibilité OpenAI/lazy proxy en environnement hétérogène.
3. **P1**: figer une stratégie de baseline sources (FR vs internationale) et réaligner les tests.
4. **P1**: stabiliser l'environnement CI pour Playwright.
5. **P2**: ajouter un test de non-régression dédié au dedup collector sous charge.

## Commandes exécutées

- `pytest -q`
- `pytest -q tests/phase4/test_load_concurrent.py::TestConcurrentCollector::test_all_21_sources_parallel_no_deadlock tests/phase4/test_scoring_memory_analyzer.py::TestAnalyzerFallback::test_analyze_job_handles_openai_error`
- revue manuelle de:
  - `agents/collector.py`
  - `config/settings.py`
  - `agents/analyzer.py`
  - `requirements.txt`
