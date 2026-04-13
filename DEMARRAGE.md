# Démarrage rapide — Facial Recognition System

## Prérequis
- Docker + Docker Compose v2
- GPU NVIDIA + drivers 525+ + CUDA 11.8 (optionnel en dev, requis en prod)
- 16 Go RAM minimum

---

## 1. Cloner et configurer

```bash
git clone https://github.com/artkabis/llm_images.git
cd llm_images
git checkout claude/facial-recognition-system-bLZRZ

# Copier les variables d'environnement de développement
cp .env.dev .env
```

---

## 2. Configurer les caméras

Éditer `config/cameras.yml` avec vos URLs RTSP ou device IDs USB.
Pour tester sans caméra, commenter toutes les entrées : le système démarrera sans flux vidéo.

---

## 3. Démarrer les services

```bash
# Démarrage complet (avec GPU)
docker compose up --build -d

# Démarrage sans GPU (développement CPU)
INSIGHTFACE_CTX_ID=-1 docker compose up --build -d

# Suivre les logs
docker compose logs -f api ml video
```

---

## 4. Accès aux interfaces

| Interface | URL | Identifiants |
|---|---|---|
| Dashboard principal | http://localhost | admin@facerec.local / admin (à créer) |
| Grafana (monitoring) | http://localhost:3001 | admin / admin |
| MLflow (tracking) | http://localhost:5000 | — |
| API docs (dev) | http://localhost:8000/api/docs | — |

---

## 5. Créer le premier utilisateur admin

```bash
docker compose exec api python -c "
import asyncio
from core.database import init_db, AsyncSessionLocal, User
from core.security import hash_password

async def create_admin():
    await init_db()
    async with AsyncSessionLocal() as db:
        user = User(
            email='admin@facerec.local',
            hashed_password=hash_password('ChangeMe123!'),
            role='admin'
        )
        db.add(user)
        await db.commit()
        print('Admin créé :', user.email)

asyncio.run(create_admin())
"
```

---

## 6. Vérifier la santé du système

```bash
curl http://localhost/health
# → {"status": "ok", "version": "1.0.0"}

curl http://localhost/api/v1/monitoring/health \
  -H "Authorization: Bearer <votre_token>"
```

---

## 7. Premier profil (test)

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost/api/v1/auth/login \
  -d "username=admin@facerec.local&password=ChangeMe123!" \
  | jq -r .access_token)

# Enrôler un profil avec 3 photos
curl -X POST http://localhost/api/v1/profiles/ \
  -H "Authorization: Bearer $TOKEN" \
  -F "name=Test Utilisateur" \
  -F "role=Employé" \
  -F "photos=@photo1.jpg" \
  -F "photos=@photo2.jpg" \
  -F "photos=@photo3.jpg"
```

---

## 8. Arrêter le système

```bash
docker compose down
# Avec suppression des volumes (ATTENTION : supprime toutes les données)
docker compose down -v
```

---

## Structure des données

```
data/
├── db/          ← Base SQLite (profils, alertes, review)
├── faiss/       ← Index vectoriel des embeddings
├── secure_frames/ ← Captures des incidents
├── active_learning/ ← Files de review active learning
└── audit_logs/  ← Logs chiffrés (rétention 90j)
```

> **Note sécurité :** Ne jamais exposer les ports 8000, 8001, 8002, 6379, 9090
> directement sur internet. Tout passe par Nginx (port 80/443).
