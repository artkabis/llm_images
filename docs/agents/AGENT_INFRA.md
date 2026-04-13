# Agent Infra — Instructions

**Rôle :** Déploiement, conteneurisation, monitoring infrastructure, migration local→VPS et scaling.

---

## 1. Responsabilités

- Maintenir la configuration Docker Compose (local) et les manifestes de déploiement (VPS)
- Surveiller les ressources système (CPU, GPU, RAM, disque, réseau)
- Alerter sur les goulots de performance et planifier le scaling
- Gérer les sauvegardes, la rotation des logs et les mises à jour
- Documenter et exécuter la procédure de migration local→VPS
- Maintenir les pipelines CI/CD (GitHub Actions)

---

## 2. Stack technique

| Outil | Usage |
|---|---|
| Docker + Docker Compose 2.x | Conteneurisation locale |
| Nginx | Reverse proxy, TLS, load balancing |
| Prometheus | Collecte métriques |
| Grafana | Dashboards infra |
| Loki | Agrégation logs |
| Promtail | Agent de collecte logs |
| GitHub Actions | CI/CD automatisé |
| Let's Encrypt / Certbot | Certificats TLS (phase VPS) |

---

## 3. Architecture Docker Compose (Phase 1 — Local)

```yaml
# docker-compose.yml — structure logique

services:
  nginx:          # Reverse proxy — port 80/443
  api:            # FastAPI — port 8000 (interne)
  worker-high:    # Celery queue haute priorité (enrôlement, identification)
  worker-low:     # Celery queue basse priorité (training, rapports)
  redis:          # Broker + cache — port 6379 (interne)
  db:             # SQLite via volume OU PostgreSQL
  ml:             # Service PyTorch + InsightFace (GPU passthrough)
  video:          # Workers OpenCV (accès /dev/video*)
  frontend:       # React build statique servi par Nginx
  mlflow:         # Tracking server — port 5000 (interne)
  prometheus:     # Métriques — port 9090 (interne)
  grafana:        # Dashboards — port 3001 (interne)
  loki:           # Logs — port 3100 (interne)
  promtail:       # Collecte logs Docker

volumes:
  db_data:        # Données SQLite / PostgreSQL
  ml_models:      # Modèles PyTorch + checkpoints
  faiss_index:    # Index vectoriel FAISS
  mlflow_data:    # Expériences MLflow
  secure_frames:  # Captures incidents (chiffrées)
  audit_logs:     # Audit logs chiffrés
```

### 3.1 Prérequis matériels (local)
- OS : Ubuntu 22.04 LTS (recommandé) ou Debian 12
- CPU : 8 cœurs minimum
- RAM : 16 Go minimum (32 Go recommandé)
- GPU : NVIDIA avec 8 Go VRAM, drivers 525+, CUDA 11.8+
- Stockage : 500 Go SSD NVMe
- Réseau : accès LAN aux caméras IP

---

## 4. Surveillance des ressources

### 4.1 Seuils d'alerte
| Ressource | Warning | Critical | Action |
|---|---|---|---|
| CPU | > 75% / 5min | > 85% / 5min | Scale workers |
| RAM | > 70% | > 80% | Restart workers + alerte |
| GPU VRAM | > 80% | > 90% | Réduire batch size + alerte |
| Disque | > 70% | > 85% | Nettoyage + alerte |
| Réseau RX/TX | > 800 Mbps | > 950 Mbps | Alerte congestion |
| Latence API p99 | > 300ms | > 500ms | Alerte + diagnostic |
| Queue Celery | > 50 tâches | > 100 tâches | Scale workers |

### 4.2 Dashboards Grafana
- **Vue système** : CPU/RAM/GPU/disque en temps réel
- **Vue réseau** : throughput, latences, erreurs
- **Vue applicative** : latences API, queue Celery, taux d'erreur
- **Vue ML** : FAR/FRR, latence inférence, drift score
- **Vue caméras** : FPS effectif, statut, qualité par caméra
- **Vue sécurité** : alertes, tentatives auth, IPs bloquées

---

## 5. Gestion des logs

- Tous les services loguent en JSON structuré (stdout → Promtail → Loki)
- Niveaux : DEBUG (dev) / INFO / WARNING / ERROR / CRITICAL
- Rotation automatique : 7 jours en local, 30 jours sur VPS
- Audit logs séparés (append-only, chiffrés, rétention 90 jours)
- Corrélation logs/métriques via trace_id dans chaque requête

---

## 6. CI/CD (GitHub Actions)

### 6.1 Pipeline de test (sur chaque PR)
```
Lint (ruff + black) → Tests unitaires (pytest) → Tests intégration
→ Build image Docker → Scan sécurité (Trivy) → Report
```

### 6.2 Pipeline de déploiement (sur merge main)
```
Tests complets → Build images → Push registry
→ Deploy staging → Smoke tests → Deploy production → Health check
```

---

## 7. Migration Local → VPS (Phase 2)

### 7.1 Checklist pré-migration
- [ ] VPS provisionné (min : 8 vCPU, 32 Go RAM, GPU optionnel, 500 Go SSD)
- [ ] Domaine configuré avec DNS
- [ ] Clés SSH déployées
- [ ] Variables d'environnement migrées (secrets manager ou .env chiffré)

### 7.2 Étapes de migration
1. Exporter dump SQLite → PostgreSQL
2. Exporter index FAISS → Qdrant (script de migration fourni)
3. Exporter modèles MLflow
4. Configurer Nginx + Let's Encrypt sur VPS
5. Déployer Docker Compose sur VPS
6. Valider avec smoke tests
7. Pointer DNS vers VPS
8. Désactiver instance locale (après 48h de stabilité)

### 7.3 Rollback
- Conserver l'instance locale opérationnelle 48h après migration
- Snapshot VPS avant chaque mise à jour majeure
- Procédure de rollback documentée et testée

---

## 8. Sauvegardes

| Donnée | Fréquence | Rétention | Destination |
|---|---|---|---|
| Base SQLite/PostgreSQL | Quotidienne | 30 jours | Volume externe |
| Index FAISS/Qdrant | Quotidienne | 7 jours | Volume externe |
| Modèles MLflow | Après chaque training | Indéfini | Volume externe |
| Audit logs | Hebdomadaire | 90 jours | Stockage froid |
| Config Docker Compose | Après chaque modif | Git | GitHub |

---

## 9. Métriques exposées

| Métrique | Type | Description |
|---|---|---|
| `node_cpu_usage_percent` | Gauge | Usage CPU global |
| `node_memory_usage_bytes` | Gauge | RAM utilisée |
| `node_disk_usage_percent` | Gauge | Disque utilisé par volume |
| `gpu_memory_used_bytes` | Gauge | VRAM GPU utilisée |
| `docker_container_restarts` | Counter | Redémarrages par service |
| `backup_last_success_timestamp` | Gauge | Timestamp dernière sauvegarde OK |
