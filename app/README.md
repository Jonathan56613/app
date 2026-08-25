# Éclair Live ⚡

Carte de foudre en temps réel : impacts des dernières 1h ou 3h, éclair le
plus proche de ta position, mise à jour toutes les 8 secondes.

Données : réseau communautaire gratuit [Blitzortung.org](https://www.blitzortung.org)
(aucune clé API nécessaire).

## Structure

```
app/
├── main.py          # backend FastAPI (se connecte au flux temps réel, expose l'API)
├── requirements.txt
└── static/
    └── index.html   # frontend (carte Leaflet + panneau temps réel)
```

## Tester en local

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Puis ouvre http://localhost:8000

## Héberger gratuitement (accessible depuis ton téléphone)

**Render.com** est le plus simple pour démarrer, gratuit, sans carte bancaire :

1. Crée un compte sur https://render.com
2. Mets ce dossier `app/` dans un repo GitHub (public ou privé)
3. Sur Render : **New +** → **Web Service** → connecte ton repo
4. Configure :
   - **Build command** : `pip install -r requirements.txt`
   - **Start command** : `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance type** : Free
5. Déploie. Tu obtiens une URL du type `https://ton-app.onrender.com`,
   accessible depuis ton téléphone (ajoute-la à l'écran d'accueil pour
   un rendu "app").

### ⚠️ Limite du plan gratuit Render
Le service s'endort après ~15 min sans visite, et met 30-50s à se
réveiller au prochain accès (le temps de rouvrir la connexion au flux
Blitzortung). C'est normal, pas un bug. Alternatives sans ce problème
mais avec carte bancaire requise (paliers gratuits) : Fly.io, Railway.

## Pistes d'amélioration (si tu veux aller plus loin)
- Notification push quand un éclair tombe à moins de X km
- Historique persistant (base SQLite au lieu de la mémoire, perdue au redémarrage)
- Filtrer par zone géographique visible sur la carte plutôt que tout charger
