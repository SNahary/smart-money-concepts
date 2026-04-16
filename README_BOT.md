# SMC Signal Bot

Bot indicateur Smart Money Concepts (SMC/ICT) avec notifications Telegram et dashboard web.

Analyse le marche en continu, detecte les Order Blocks en confluence avec le biais de structure (BOS/CHoCH) et envoie des signaux complets (Entry, SL, TP, R:R) sur Telegram lorsque le prix revient dans un OB.

> **Ce bot ne passe aucun ordre.** C'est un outil de notification qui vous alerte quand votre strategie matche avec le marche.

---

## Table des matieres

- [Strategie](#strategie)
- [Prerequis](#prerequis)
- [Installation](#installation)
- [Configuration](#configuration)
  - [1. Telegram](#1-telegram)
  - [2. Data Provider](#2-data-provider)
  - [3. Fichier .env](#3-fichier-env)
- [Lancement](#lancement)
- [Dashboard](#dashboard)
- [Architecture](#architecture)
- [Parametres de la strategie](#parametres-de-la-strategie)
- [Timezone et DST](#timezone-et-dst)
- [Structure des fichiers](#structure-des-fichiers)
- [Troubleshooting](#troubleshooting)

---

## Strategie

```
1. Biais HTF (4H par defaut)
   Le dernier BOS ou CHoCH sur le timeframe de biais determine la direction.
   CHoCH > BOS (signal plus fort).

2. Recherche d'Order Blocks (30M par defaut)
   Seuls les OBs en confluence avec le biais sont retenus.
   OB bullish si biais bullish, OB bearish si biais bearish.
   Seuls les OBs non mitiges (encore actifs) sont consideres.

3. Detection du retour sur l'OB
   Bullish : le low de la bougie courante entre dans la zone OB (low <= OB Top)
   Bearish : le high de la bougie courante entre dans la zone OB (high >= OB Bottom)

4. Notification
   Envoi Telegram + affichage dans le dashboard avec :
   Entry, SL, TP1 (prochain swing), TP2 (previous high/low HTF), R:R, force de l'OB.
```

---

## Prerequis

| Composant | Version minimum | Notes |
|-----------|-----------------|-------|
| **Python** | 3.10+ | `zoneinfo` requis (stdlib depuis 3.9) |
| **OS** | Windows 10/11 | Requis si MetaTrader 5 est utilise comme data provider |
| **pip** | 22+ | Pour installer les dependances |
| **MetaTrader 5** | Terminal installe + compte demo | Option A — gratuit, zero rate limit |
| **OANDA** | Compte practice (gratuit) | Option B — cross-platform, REST API |
| **Telegram** | Bot cree via @BotFather | Pour recevoir les notifications |

---

## Installation

### 1. Cloner le projet

```bash
git clone <url-du-repo>
cd smart-money-concepts
```

### 2. Creer un environnement virtuel (recommande)

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 3. Installer les dependances

```bash
pip install -r requirements.txt
```

### 4. Si vous utilisez MetaTrader 5

```bash
pip install MetaTrader5
```

> MetaTrader5 est un package Windows uniquement. Assurez-vous que le terminal MT5 est installe et en cours d'execution.

---

## Configuration

### 1. Telegram

#### Creer le bot

1. Ouvrir Telegram et chercher **@BotFather**
2. Envoyer `/newbot`
3. Choisir un nom (ex: `SMC Signal Bot`) et un username (ex: `smc_signal_bot`)
4. BotFather retourne un **token** de la forme `7123456789:AAHfiqks...`

#### Recuperer votre chat_id

1. Envoyer un message quelconque a votre bot
2. Ouvrir dans un navigateur :
   ```
   https://api.telegram.org/bot<VOTRE_TOKEN>/getUpdates
   ```
3. Dans la reponse JSON, trouver `"chat":{"id": 123456789}` — c'est votre **chat_id**

#### Pour un channel/groupe

- Ajouter le bot comme administrateur du channel
- Le chat_id sera `@nom_du_channel` ou un ID numerique negatif (commence par `-100`)

### 2. Data Provider

Deux options disponibles, choisissez celle qui vous convient :

#### Option A : MetaTrader 5 (recommande sur Windows)

| Avantage | Detail |
|----------|--------|
| Zero rate limit | Donnees en local via IPC |
| Toutes les paires | EURUSD, GBPUSD, XAUUSD + tout ce que le broker propose |
| Temps reel | Donnees live du broker |

**Setup :**
1. Installer [MetaTrader 5](https://www.metatrader5.com/fr/download)
2. Creer un compte demo chez un broker MT5 (IC Markets, Pepperstone, XM...)
3. Se connecter dans le terminal MT5
4. Laisser le terminal ouvert pendant que le bot tourne
5. Noter le **login** (numero de compte), **password** et **server** (ex: `ICMarketsSC-Demo`)

#### Option B : OANDA REST API (cross-platform)

| Avantage | Detail |
|----------|--------|
| Cross-platform | Fonctionne sur Windows, Linux, macOS |
| Pas de logiciel | Simple appel REST, rien a installer |
| 5000 bougies/requete | Historique profond |

**Setup :**
1. Creer un compte practice (gratuit) sur [oanda.com](https://www.oanda.com)
2. Aller dans `My Account > My Services > Manage API Access`
3. Generer un **API token**
4. Noter votre **Account ID** (visible dans la page du compte)

### 3. Fichier .env

Copier le template et remplir avec vos credentials :

```bash
cp .env.example .env
```

Editer `.env` :

```env
# ===== TELEGRAM =====
TELEGRAM_BOT_TOKEN=7123456789:AAHfiqksKZ8WmR2zMfghS0jB3v4x5y6z7w8
TELEGRAM_CHAT_ID=123456789

# ===== MT5 (Option A) =====
MT5_LOGIN=12345678
MT5_PASSWORD=votre_mot_de_passe_demo
MT5_SERVER=ICMarketsSC-Demo

# ===== OANDA (Option B) =====
OANDA_API_TOKEN=votre_token_practice
OANDA_ACCOUNT_ID=101-001-12345678-001
OANDA_ENVIRONMENT=practice

# ===== GENERAL =====
DATA_PROVIDER=mt5
TIMEZONE=Europe/Helsinki
```

> **Important :** Le fichier `.env` contient des secrets. Il est dans le `.gitignore` et ne sera jamais commite.

---

## Lancement

```bash
python run.py
```

Le dashboard s'ouvre automatiquement sur :

```
http://localhost:8080
```

### Demarrage du scan

1. Ouvrir le dashboard dans un navigateur
2. Verifier/ajuster la configuration dans le panneau de gauche
3. Cliquer **Start**
4. Le bot scanne toutes les 5 minutes (configurable)
5. Les signaux apparaissent dans le dashboard ET sur Telegram

### Arreter le bot

- Cliquer **Stop** dans le dashboard
- Ou `Ctrl+C` dans le terminal

---

## Dashboard

Le dashboard NiceGUI est divise en deux zones :

### Panneau de gauche — Configuration

| Parametre | Description | Defaut |
|-----------|-------------|--------|
| Data Provider | `mt5` ou `oanda` | `mt5` |
| Timezone | `UTC` ou `Broker (UTC+2/+3 auto DST)` | Broker |
| Paires | Multi-selection des paires a surveiller | EURUSD, GBPUSD, XAUUSD |
| TF Biais | Timeframe pour le biais de structure | 4H |
| TF Order Block | Timeframe pour la recherche d'OB | 30M |
| Swing Length (Biais) | Sensibilite des swing points HTF | 10 |
| Swing Length (OB) | Sensibilite des swing points OB TF | 10 |
| R:R minimum | Filtre — n'envoie que si R:R >= seuil | 2.0 |
| Buffer SL (pips) | Marge supplementaire sous/au-dessus du SL | 5.0 |
| Intervalle de scan | Frequence en secondes | 300 (5 min) |

> Les parametres de strategie sont **persistants** — ils sont sauvegardes dans `bot/data/strategy_config.json` et restaures au prochain lancement.

### Panneau de droite — Monitoring

- **Biais Marche** : cartes par paire montrant la direction (Bullish/Bearish/Neutre) et le type (BOS/CHoCH)
- **Order Blocks Actifs** : tableau des OBs non mitiges en confluence avec le biais
- **Historique des Signaux** : les 20 derniers signaux envoyes avec Entry, SL, TP, R:R

---

## Architecture

```
Scan toutes les 5 minutes (configurable)
         |
         v
   Pour chaque paire :
         |
    [1] Fetch OHLCV bias TF + OB TF          (MT5 ou OANDA)
         |
    [2] Calculer le biais via BOS/CHoCH       (smc.bos_choch)
         |
    [3] Scanner les OBs en confluence          (smc.ob, filtre par direction)
         |
    [4] Detecter le retour du prix sur l'OB   (comparaison prix courant / zone OB)
         |
    [5] Calculer Entry/SL/TP1/TP2/R:R         (swing highs/lows + previous high/low)
         |
    [6] Verifier le dedup                      (SQLite — pas de double notification)
         |
    [7] Envoyer Telegram + sauver en DB        (requests POST + aiosqlite)
```

### Librairie SMC existante (socle)

Le bot utilise les fonctions existantes de `smartmoneyconcepts` sans les modifier :

| Fonction | Usage dans le bot |
|----------|-------------------|
| `smc.swing_highs_lows()` | Foundation pour BOS/CHoCH, OB, et calcul TP |
| `smc.bos_choch()` | Determination du biais HTF |
| `smc.ob()` | Detection des Order Blocks sur le TF OB |
| `smc.previous_high_low()` | Calcul du TP2 (target HTF) |

---

## Parametres de la strategie

### Calcul du trade

#### Signal ACHAT (OB Bullish)

| Champ | Calcul |
|-------|--------|
| Entry | Haut de l'OB (`OB.Top`) |
| SL | Bas de l'OB - buffer en pips (`OB.Bottom - buffer`) |
| TP1 | Prochain swing high au-dessus de l'entry (TF OB) |
| TP2 | Previous High du TF de biais |
| R:R | `(TP - Entry) / (Entry - SL)` |

#### Signal VENTE (OB Bearish)

| Champ | Calcul |
|-------|--------|
| Entry | Bas de l'OB (`OB.Bottom`) |
| SL | Haut de l'OB + buffer en pips (`OB.Top + buffer`) |
| TP1 | Prochain swing low en-dessous de l'entry (TF OB) |
| TP2 | Previous Low du TF de biais |

### Filtres

- **R:R minimum** : le signal est ignore si le R:R calcule est inferieur au seuil (defaut 1:2)
- **Deduplication** : un OB deja notifie n'est pas renvoye (persistant 7 jours en DB)
- **Force OB** : le pourcentage de force est affiche (ratio volume buy/sell) mais pas filtre par defaut

### Valeurs de pip par symbole

| Symbole | 1 pip |
|---------|-------|
| EURUSD, GBPUSD, etc. | 0.0001 |
| XAUUSD (Gold) | 0.1 |

---

## Timezone et DST

Les brokers forex utilisent generalement le fuseau horaire **EET/EEST** :

| Periode | Heure serveur | UTC offset |
|---------|---------------|------------|
| Heure d'hiver (oct → mars) | EET | UTC+2 |
| Heure d'ete (mars → oct) | EEST | UTC+3 |

Le bot utilise `Europe/Helsinki` qui gere automatiquement le passage heure d'ete/hiver (DST). Cela impacte :

- **Les limites des bougies daily/weekly** (quand commence/finit un "jour")
- **Le Previous High/Low** (qui depend des limites de periode)
- **L'horodatage dans les notifications Telegram**

Si vous preferez rester en UTC pur (pas de DST), selectionnez `UTC` dans le dashboard.

---

## Structure des fichiers

```
smart-money-concepts/
|
|-- smartmoneyconcepts/              # Librairie SMC existante (inchangee)
|   |-- __init__.py
|   |-- smc.py                      # 8 indicateurs SMC
|
|-- bot/                             # Bot signal
|   |-- config.py                    # EnvSettings (.env) + StrategyConfig (JSON)
|   |-- scanner.py                   # Boucle principale du scan
|   |-- state.py                     # SQLite : dedup + historique
|   |-- data_providers/
|   |   |-- base.py                  # Interface abstraite DataProvider
|   |   |-- mt5_provider.py          # MetaTrader 5
|   |   |-- oanda_provider.py        # OANDA REST API
|   |-- strategy/
|   |   |-- bias.py                  # Biais via BOS/CHoCH
|   |   |-- ob_scanner.py            # Scan OBs + detection retour prix
|   |   |-- trade_calculator.py      # Calcul Entry/SL/TP/RR
|   |-- notifier/
|   |   |-- telegram.py              # Envoi via Telegram Bot API
|   |-- ui/
|   |   |-- dashboard.py             # Dashboard NiceGUI
|   |-- data/
|       |-- strategy_config.json     # Config strategie (genere par le dashboard)
|       |-- bot_state.db             # SQLite (genere au runtime)
|
|-- .env.example                     # Template des credentials
|-- .env                             # Vos credentials (JAMAIS commite)
|-- requirements.txt                 # Dependances Python
|-- run.py                           # Point d'entree
|-- README.md                        # Doc librairie SMC
|-- README_BOT.md                    # Ce fichier
```

---

## Troubleshooting

### Le bot ne se connecte pas a MT5

- Verifier que le terminal MetaTrader 5 est **ouvert et connecte** au broker
- Verifier que le login/password/server dans `.env` correspondent au compte demo
- Le package `MetaTrader5` ne fonctionne que sur **Windows**
- Essayer dans un terminal Python :
  ```python
  import MetaTrader5 as mt5
  mt5.initialize()
  print(mt5.last_error())
  ```

### Le bot ne se connecte pas a OANDA

- Verifier que `OANDA_ENVIRONMENT=practice` est bien configure
- Verifier que le token API est valide (le regenerer si besoin)
- Tester l'acces :
  ```bash
  curl -H "Authorization: Bearer VOTRE_TOKEN" \
       https://api-fxpractice.oanda.com/v3/accounts
  ```

### Pas de signal recu sur Telegram

1. Verifier que le bot token et chat_id sont corrects dans `.env`
2. Envoyer un message a votre bot d'abord (necessaire pour activer la conversation)
3. Verifier que le R:R minimum n'est pas trop eleve (baisser a 1.0 pour tester)
4. Verifier les logs dans le terminal pour les erreurs
5. Tester l'envoi :
   ```bash
   curl -X POST "https://api.telegram.org/botVOTRE_TOKEN/sendMessage" \
        -d "chat_id=VOTRE_CHAT_ID&text=test"
   ```

### Les noms de paires ne sont pas trouves (MT5)

Les noms de symboles varient selon le broker :
- IC Markets : `EURUSD`, `XAUUSD`
- Pepperstone : `EURUSD.`, `XAUUSD.`
- XM : `EURUSDm`, `GOLDm`

Verifier les noms exacts dans le terminal MT5 (fenetre "Market Watch") et ajuster dans le dashboard.

### Le dashboard ne s'ouvre pas

- Verifier que le port 8080 n'est pas utilise : `netstat -an | findstr 8080`
- Essayer avec un autre port en modifiant `ui.run(port=8081)` dans `bot/ui/dashboard.py`
- Verifier que `nicegui` est installe : `pip install nicegui`

### Erreurs de timezone

- Si les bougies daily ne correspondent pas a votre broker, basculer entre `UTC` et `Broker` dans le dashboard
- Les timestamps MT5 sont en UTC ; le bot les convertit automatiquement selon le timezone configure

---

## Disclaimer

Ce bot est un outil d'aide a la decision. Il ne passe aucun ordre et ne constitue pas un conseil en investissement. Utilisez toujours une gestion de risque appropriee et faites vos propres analyses avant de prendre position. L'auteur n'est pas responsable des pertes eventuelles.
