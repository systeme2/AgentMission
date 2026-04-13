# 🚀 Guide de déploiement — Mission Agent v2

---

## Railway (recommandé — daemon continu)

Railway fait tourner un process long (`python main.py loop`) en continu, avec redémarrage automatique, logs en temps réel, et volume persistant pour la SQLite.

### Étape 1 — Créer le compte et le projet

1. Va sur **railway.app** → "Start a New Project"
2. Choisis **"Deploy from GitHub repo"**
3. Autorise Railway à accéder à ton GitHub
4. Sélectionne le repo `mission-agent`

Railway détecte automatiquement le `Dockerfile` et le `railway.toml`.

### Étape 2 — Configurer le volume persistant (SQLite)

La base SQLite doit survivre aux redémarrages.

1. Dans ton projet Railway → onglet **"Volumes"**
2. Clique **"Add Volume"**
3. Mount Path : `/app/data`
4. Valide

Sans volume, les missions vues sont perdues à chaque redémarrage (tu recevras des doublons).

### Étape 3 — Variables d'environnement

Dans Railway → onglet **"Variables"**, ajoute :

```
# Obligatoires
TELEGRAM_TOKEN        = 1234567890:ABCdef...
TELEGRAM_CHAT_ID      = 123456789

# Fortement recommandés
OPENAI_API_KEY        = sk-...

# Profil et comportement
ACTIVE_PROFILE        = all          # all | wordpress | react | seo | international
TELEGRAM_BOT_ENABLED  = true
SEMANTIC_SCORING      = true
LOOP_INTERVAL         = 300          # secondes entre les cycles (300 = 5 min)
REQUEST_DELAY         = 2            # délai entre requêtes (secondes)

# Optionnels
TWITTER_BEARER_TOKEN  = ...
GITHUB_TOKEN          = ...
IDEAL_PROFILE_TEXT    = Expert React senior remote uniquement budget minimum 400€
```

**Ne pas mettre** `DB_PATH` — il est déjà configuré dans le Dockerfile vers `/app/data/missions.db`.

### Étape 4 — Déployer

Railway déclenche un build automatiquement dès que tu pousses sur `main`.

Pour un déploiement manuel :
```bash
# Installer Railway CLI
npm install -g @railway/cli

# Login
railway login

# Déployer depuis ton terminal local
railway up
```

### Étape 5 — Vérifier

```bash
# Logs en temps réel
railway logs

# Tu dois voir :
# ╔══════════════════════════════════════════════╗
# ║        🤖  MISSION AGENT  v2.0              ║
# ╚══════════════════════════════════════════════╝
# ✅ Base de données initialisée
# 📡 [TelegramBot] Polling démarré...
# 🔄 CYCLE #1 — ...
# 📡 COLLECTOR — Lancement des sources...
```

### Coûts Railway

- **Hobby plan** : 5$/mois — suffisant pour cet agent (usage CPU très faible entre les cycles)
- **Free tier** : 500h/mois — environ 20 jours, pas assez pour tourner en continu
- Recommandation : Hobby plan à 5$/mois

---

## Fly.io (alternative gratuite)

Fly.io a un tier gratuit généreux avec 3 VMs (256 MB RAM chacune).

### Setup

```bash
# Installer flyctl
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Créer l'app (depuis le dossier du projet)
fly launch --name mission-agent --region cdg  # cdg = Paris

# Ça génère un fly.toml automatiquement
```

### fly.toml minimal

```toml
app = "mission-agent"
primary_region = "cdg"

[build]

[env]
  DB_PATH = "/data/missions.db"
  ACTIVE_PROFILE = "all"
  TELEGRAM_BOT_ENABLED = "true"

[[mounts]]
  source = "mission_data"
  destination = "/data"

[[vm]]
  memory = "256mb"
  cpu_kind = "shared"
  cpus = 1
```

### Variables secrètes (équivalent de .env)

```bash
fly secrets set TELEGRAM_TOKEN="1234567890:ABCdef..."
fly secrets set TELEGRAM_CHAT_ID="123456789"
fly secrets set OPENAI_API_KEY="sk-..."
```

### Volume persistant

```bash
fly volumes create mission_data --region cdg --size 1
```

### Déployer

```bash
fly deploy
fly logs   # voir les logs
```

---

## VPS (Hetzner/OVH/Scaleway) — option full control

Si tu veux héberger toi-même sur un serveur à 4€/mois :

```bash
# Sur le VPS (Ubuntu 22.04)
apt update && apt install -y python3 python3-pip python3-venv git

git clone https://github.com/toi/mission-agent.git
cd mission-agent
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Créer le .env
cp .env.example .env
nano .env  # remplir les variables

# Lancer en background avec systemd
cat > /etc/systemd/system/mission-agent.service << 'EOF'
[Unit]
Description=Mission Agent v2
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/mission-agent
EnvironmentFile=/root/mission-agent/.env
ExecStart=/root/mission-agent/venv/bin/python main.py loop
Restart=on-failure
RestartSec=30
StandardOutput=append:/var/log/mission-agent.log
StandardError=append:/var/log/mission-agent.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable mission-agent
systemctl start mission-agent

# Voir les logs
journalctl -u mission-agent -f
# ou
tail -f /var/log/mission-agent.log
```

---

## Pourquoi pas Vercel ?

Vercel exécute des **fonctions sans état** qui s'arrêtent après quelques secondes (max 10s sur le plan gratuit, 300s sur Pro). `python main.py loop` tourne en continu — il serait tué immédiatement. Vercel est fait pour des APIs HTTP et des sites web, pas des daemons.

---

## Checklist avant de déployer

- [ ] `TELEGRAM_TOKEN` et `TELEGRAM_CHAT_ID` configurés
- [ ] Test local réussi : `python main.py test`
- [ ] Volume persistant monté sur `/app/data`
- [ ] `OPENAI_API_KEY` configuré (optionnel mais recommandé)
- [ ] `ACTIVE_PROFILE` choisi selon tes besoins
- [ ] Premier cycle observé dans les logs
- [ ] Première notification Telegram reçue
