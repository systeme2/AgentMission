# 🤖 Mission Agent v2 — Trouve tes missions freelance automatiquement

Système d'agents IA qui scrape **23 sources**, analyse les missions avec GPT-4o-mini, les score selon tes préférences (+ embeddings sémantiques), et t'envoie les meilleures sur **Telegram avec boutons interactifs**.

---

## ✨ Features v2

### 🤖 Bot Telegram bidirectionnel
- **7 commandes** : `/start` `/stats` `/top5` `/status` `/pause` `/resume` `/seuil`
- **Boutons inline** 👍 👎 📝 sur chaque notification — un tap = feedback enregistré
- **Mémoire adaptive** : chaque like/dislike ajuste le scoring futur
- **Pause à la volée** : `/pause 60` met l'agent en pause 60 min

### 🧠 Scoring sémantique (embeddings)
- Embeddings **OpenAI text-embedding-3-small** — similarité cosinus entre chaque mission et ton profil idéal
- **Bonus 0–20%** ajouté au score mots-clés existant
- Cache MD5 pour éviter les appels API redondants
- Fallback silencieux si pas de clé OpenAI

### 🎯 Multi-profils
- **5 profils** prédéfinis : `all` · `wordpress` · `react` · `seo` · `international`
- Chaque profil a ses keywords, budget min, seuil, langues, sources préférées
- Le profil `international` cible Upwork / Remote OK / LinkedIn uniquement
- `python main.py loop-profile react` → démarre avec le profil React

### 🌐 23 sources
Phase 0–3 + **GitHub Jobs** (Issues API) + **RSS custom** (tes propres flux configurables)

---

## 🚀 Installation

```bash
git clone <repo> && cd mission-agent

python -m venv venv && source venv/bin/activate

pip install -r requirements.txt

# Playwright (optionnel — pour Malt)
# playwright install chromium

cp .env.example .env
# → édite .env (voir section Configuration)
```

---

## ⚙️ Configuration

### Variables d'environnement (`.env`)

```bash
# ── Obligatoires ──────────────────────────────────────────────
TELEGRAM_TOKEN=1234567890:ABCdef...       # @BotFather → /newbot
TELEGRAM_CHAT_ID=123456789               # ton user ID

# ── OpenAI (optionnel mais recommandé) ────────────────────────
OPENAI_API_KEY=sk-...                    # analyse IA + embeddings sémantiques

# ── Profil actif ──────────────────────────────────────────────
ACTIVE_PROFILE=all                       # all | wordpress | react | seo | international

# ── Bot Telegram ─────────────────────────────────────────────
TELEGRAM_BOT_ENABLED=true               # active le bot bidirectionnel

# ── Scoring sémantique ────────────────────────────────────────
SEMANTIC_SCORING=true                   # active les embeddings (nécessite OPENAI_API_KEY)
IDEAL_PROFILE_TEXT=                     # texte libre décrivant ton profil idéal
                                        # (auto-généré depuis PREFERRED_KEYWORDS si vide)

# ── Twitter/X (optionnel) ─────────────────────────────────────
TWITTER_BEARER_TOKEN=                   # developer.twitter.com → Bearer Token

# ── RSS personnalisés (optionnel) ────────────────────────────
# Ajouter dans config/settings.py → CUSTOM_RSS_FEEDS
```

### Récupérer ton `TELEGRAM_CHAT_ID`
1. Envoie un message à ton bot
2. Ouvre `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Cherche `"chat":{"id": XXXXXXX}`

### Personnaliser tes préférences (`config/settings.py`)
```python
PREFERRED_KEYWORDS = ["wordpress", "react", "nextjs", "seo", ...]
NEGATIVE_KEYWORDS  = ["stagiaire", "cobol", ...]
MIN_BUDGET         = 200    # € minimum
MIN_SCORE          = 0.4    # seuil notification (0.0–1.0)
CUSTOM_RSS_FEEDS   = [
    "https://monblog.fr/feed",
    "https://autresite.com/jobs.rss",
]
```

---

## 🎮 Utilisation

```bash
# ── Commandes de base ─────────────────────────────────────────
python main.py test       # teste la connexion Telegram
python main.py run        # un seul cycle
python main.py loop       # daemon (toutes les 5 min) + bot Telegram
python main.py status     # statistiques
python main.py missions   # dernières missions en base

# ── Multi-profils ────────────────────────────────────────────
python main.py profiles               # liste les profils disponibles
python main.py loop-profile react     # daemon avec profil React
python main.py loop-profile wordpress # daemon avec profil WordPress
python main.py loop-profile international  # sources EN uniquement
```

### Bot Telegram — commandes disponibles

| Commande | Description |
|----------|-------------|
| `/start` | Message de bienvenue + liste des commandes |
| `/stats` | Statistiques (total, envoyées, likées, par source) |
| `/top5`  | 5 meilleures missions non vues |
| `/status` | État de l'agent (actif / en pause) |
| `/pause 60` | Met en pause 60 minutes |
| `/resume` | Reprend immédiatement |
| `/seuil 0.6` | Change le seuil de score à la volée |

### Boutons inline sur chaque notification
- **👍 Intéressant** → like enregistré, score des missions similaires boosté
- **👎 Pas pour moi** → dislike enregistré, score des missions similaires réduit
- **📝 J'postule** → marqué comme postulé dans la base

---

## 📁 Structure

```
mission-agent/
├── agents/
│   ├── collector.py       # Agrège 23 sources en parallèle
│   ├── analyzer.py        # Analyse IA (GPT-4o-mini) + fallback mots-clés
│   ├── scorer.py          # Score 0–100% multi-critères + mémoire + sémantique
│   ├── notifier.py        # Telegram avec boutons inline
│   └── semantic_scorer.py # Embeddings OpenAI + cosine similarity
├── core/
│   ├── orchestrator.py    # Pipeline : collect→analyze→score→notify
│   ├── database.py        # SQLite : missions, préférences, feedback
│   ├── memory.py          # Apprentissage like/dislike
│   └── telegram_bot.py    # Bot bidirectionnel polling
├── sources/               # 23 scrapers
├── config/
│   ├── settings.py        # Paramètres + variables d'env
│   └── profiles.py        # 5 profils multi-sources
├── tests/
│   ├── phase1/  (89 tests)
│   ├── phase2/  (81 tests)
│   ├── phase3/  (132 tests)
│   ├── phase4/  (191 tests)
│   └── upgrades/ (134 tests)
├── .github/workflows/ci.yml
├── Dockerfile
└── main.py
```

---

## 🌐 Les 23 sources

| Phase | Source | Méthode | Note |
|-------|--------|---------|------|
| 0 | Codeur.com | BeautifulSoup | Principal FR |
| 0 | Reddit | API JSON | /r/forhire, /r/freelance |
| 0 | WeLoveDevs | API REST | Remote FR |
| 0 | RemixJobs | RSS | Freelance FR |
| 1 | Freelance.com | BeautifulSoup | |
| 1 | 404Works | BeautifulSoup | |
| 1 | ComeUp | BeautifulSoup | |
| 1 | BeFreelancr | BeautifulSoup | |
| 1 | Collective.work | JSON + HTML | |
| 2 | Malt | Playwright + fallback | JS-rendered |
| 2 | Upwork | RSS public | International |
| 2 | Remote OK | API JSON | Remote worldwide |
| 2 | Freelancer.com | API REST | International |
| 2 | Fiverr | JSON-LD | |
| 2 | Toptal | BeautifulSoup | |
| 2 | Kicklox | BeautifulSoup | Tech FR |
| 3 | HackerNews | API Algolia | Who is Hiring |
| 3 | Dev.to | API REST | #hiring |
| 3 | LinkedIn | JobSpy + HTML | |
| 3 | Twitter/X | API v2 + Nitter RSS | Optionnel |
| 3 | IndieHackers | Next.js data | Startups |
| ★ | GitHub Jobs | Issues API | Tech remote |
| ★ | RSS Custom | RSS 2.0 + Atom | Configurables |

---

## 🎯 Profils disponibles

```bash
python main.py profiles
```

| Profil | Spécialité | Sources | Budget min | Seuil |
|--------|-----------|---------|-----------|-------|
| `all` | Généraliste | 23 sources | 200€ | 40% |
| `wordpress` | WordPress / WooCommerce | 23 sources | 300€ | 45% |
| `react` | React / Next.js | 23 sources | 400€ | 50% |
| `seo` | SEO technique | 23 sources | 250€ | 45% |
| `international` | Anglophone remote | Upwork, RemoteOK, LinkedIn... | 500€ | 50% |

---

## 🧪 Tests

```bash
# Tous les tests (627)
pytest tests/ -q

# Par phase
pytest tests/phase1/ -v
pytest tests/phase2/ -v
pytest tests/phase3/ -v
pytest tests/phase4/ -v      # E2E, DB, load, régression
pytest tests/upgrades/ -v    # Bot, semantic, profils, nouvelles sources

# Avec coverage
pytest tests/ --cov=sources --cov=agents --cov=core --cov-report=term-missing
```

---

## 🐳 Docker

```bash
docker build -t mission-agent .

docker run -d \
  -e TELEGRAM_TOKEN="ton_token" \
  -e TELEGRAM_CHAT_ID="ton_chat_id" \
  -e OPENAI_API_KEY="sk-..." \
  -e ACTIVE_PROFILE="react" \
  -e TELEGRAM_BOT_ENABLED="true" \
  -v $(pwd)/data:/app/data \
  --name mission-agent \
  mission-agent

docker logs -f mission-agent
```

---

## ⚠️ Notes

- Usage **personnel uniquement** — respecte les CGU des sites
- `REQUEST_DELAY = 2s` entre requêtes pour ne pas surcharger les serveurs
- Playwright requis uniquement pour Malt : `playwright install chromium`
- JobSpy requis pour LinkedIn complet : `pip install python-jobspy`
- Sans `OPENAI_API_KEY` : analyse par mots-clés (fallback robuste), pas d'embeddings
