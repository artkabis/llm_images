# Agent Backend — Instructions

**Rôle :** Orchestration des services, exposition de l'API REST et WebSocket, gestion des tâches asynchrones.

---

## 1. Responsabilités

- Exposer l'API REST (enrôlement, identification, gestion profils, alertes)
- Gérer les connexions WebSocket pour les alertes temps réel
- Orchestrer les appels entre Agent ML/IA, Agent Sécurité et Agent Data
- Gérer la file de tâches asynchrones (Celery) pour les opérations longues
- Valider et sécuriser tous les inputs entrants
- Versionner l'API et maintenir la rétrocompatibilité

---

## 2. Stack technique

| Outil | Usage |
|---|---|
| FastAPI 0.110+ | Framework API REST + WebSocket |
| Pydantic v2 | Validation et sérialisation des données |
| SQLAlchemy 2.x | ORM base de données |
| Alembic | Migrations base de données |
| Celery 5.x | File de tâches asynchrones |
| Redis 7.x | Broker Celery + cache + pub/sub |
| SQLite / PostgreSQL | Base de données métadonnées |
| Uvicorn | Serveur ASGI production |

---

## 3. Structure de l'API

### 3.1 Endpoints REST

#### Profils
```
POST   /api/v1/profiles/           Créer un profil (upload photos)
GET    /api/v1/profiles/           Lister les profils (paginé)
GET    /api/v1/profiles/{id}       Détail d'un profil
PUT    /api/v1/profiles/{id}       Mettre à jour un profil
DELETE /api/v1/profiles/{id}       Supprimer un profil (RGPD)
POST   /api/v1/profiles/{id}/photos Ajouter des photos à un profil
```

#### Identification
```
POST   /api/v1/identify/           Identifier une image (upload)
GET    /api/v1/identify/history    Historique des identifications (paginé)
```

#### Alertes & Incidents
```
GET    /api/v1/alerts/             Lister alertes (filtres niveau/date/caméra)
GET    /api/v1/alerts/{id}         Détail d'une alerte
POST   /api/v1/alerts/{id}/ack     Acquitter une alerte
GET    /api/v1/incidents/export    Export CSV/PDF
```

#### Active Learning
```
GET    /api/v1/review/queue        File de frames à labelliser
POST   /api/v1/review/{id}/label   Soumettre un label
POST   /api/v1/training/trigger    Déclencher un fine-tuning manuel
GET    /api/v1/training/history    Historique des entraînements
```

#### Monitoring
```
GET    /api/v1/health              Santé globale du système
GET    /api/v1/metrics/ml          Métriques ML (FAR, FRR, EER, latence)
GET    /api/v1/cameras/status      Statut de toutes les caméras
GET    /api/v1/system/resources    CPU, GPU, RAM, disque
```

#### Auth
```
POST   /api/v1/auth/login          Authentification → JWT
POST   /api/v1/auth/refresh        Refresh du token
POST   /api/v1/auth/logout         Révocation du token
```

### 3.2 WebSocket
```
WS /ws/alerts          Stream alertes temps réel (toutes caméras)
WS /ws/cameras/{id}    Flux annoté d'une caméra spécifique
WS /ws/metrics         Stream métriques système temps réel
```

---

## 4. Validation des inputs

Toutes les requêtes sont validées via Pydantic v2 :
- Types stricts (pas de coercition implicite)
- Tailles maximales sur les uploads d'images (défaut : 10 Mo)
- Formats acceptés : JPEG, PNG, WEBP uniquement
- Sanitisation des champs texte (strip HTML, caractères spéciaux)
- Validation des UUIDs pour tous les identifiants

---

## 5. Gestion des tâches asynchrones (Celery)

| Tâche | Déclencheur | Priorité |
|---|---|---|
| `enroll_profile` | Upload photos profil | Haute |
| `identify_image` | Requête identification | Haute |
| `fine_tune_model` | Seuil active learning atteint / manuel | Basse |
| `generate_report` | Planifié (hebdomadaire) | Basse |
| `export_incidents` | Demande opérateur | Moyenne |
| `cleanup_old_frames` | Planifié (quotidien) | Basse |

Configuration Celery :
- Workers dédiés par priorité (queues séparées)
- Timeout par tâche (enroll: 30s, identify: 5s, fine_tune: sans limite)
- Retry automatique x3 avec backoff exponentiel
- Dead Letter Queue pour les tâches échouées

---

## 6. Gestion des erreurs

| Code | Situation |
|---|---|
| 400 | Input invalide (format, taille, type) |
| 401 | Token absent ou expiré |
| 403 | Permission insuffisante (RBAC) |
| 404 | Ressource introuvable |
| 409 | Conflit (profil déjà existant) |
| 422 | Validation Pydantic échouée |
| 429 | Rate limit dépassé |
| 503 | Service ML ou vidéo indisponible |

---

## 7. Performance

- Toutes les routes I/O-bound sont async (await)
- Connexion DB via pool SQLAlchemy (min=5, max=20)
- Cache Redis sur les endpoints fréquents (TTL configurable)
- Compression Gzip des réponses > 1 Ko
- Pagination obligatoire sur tous les endpoints de liste (défaut : 50, max : 200)
- Middleware de mesure latence → Prometheus

---

## 8. Métriques exposées

| Métrique | Type | Description |
|---|---|---|
| `api_requests_total` | Counter | Requêtes par endpoint et status |
| `api_latency_seconds` | Histogram | Latence P50/P95/P99 par endpoint |
| `api_active_websockets` | Gauge | Connexions WebSocket actives |
| `celery_tasks_pending` | Gauge | Tâches en attente par queue |
| `celery_tasks_failed` | Counter | Tâches échouées par type |
| `db_pool_connections` | Gauge | Connexions DB actives/disponibles |
