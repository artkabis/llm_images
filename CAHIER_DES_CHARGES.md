# Cahier des Charges — Système de Reconnaissance Faciale pour Vidéosurveillance d'Entreprise

**Version :** 1.0 | **Date :** 2026-04-13 | **Statut :** Draft  
**Destinataires :** Ingénieurs IA, Sécurité, Backend, Infrastructure, Frontend

---

## 1. Contexte & Objectifs

### 1.1 Contexte
Les entreprises ont besoin de contrôler l'accès physique à leurs locaux en temps réel. Les systèmes de badges traditionnels sont contournables et ne permettent pas d'identifier visuellement les individus. Ce projet propose un système de reconnaissance faciale biométrique sur flux vidéo continu, capable d'identifier les personnes autorisées et de signaler automatiquement les intrus.

### 1.2 Objectifs fonctionnels
- Ingérer des flux vidéo temps réel depuis webcams et caméras IP (RTSP)
- Détecter et identifier les visages frame par frame
- Comparer chaque visage détecté au registre des personnes autorisées
- Émettre des alertes immédiates pour toute personne non reconnue (intrus)
- Permettre l'enrôlement de nouveaux profils (multi-angles, multi-photos)
- S'améliorer en continu via active learning (human-in-the-loop)
- Fournir un dashboard de monitoring complet (métriques ML, santé système, alertes sécurité)

### 1.3 Périmètre
- **Usage :** R&D, interne entreprise
- **Échelle cible :** 1 000 à 100 000 profils
- **Déploiement :** local (phase 1) → VPS/cloud (phase 2)
- **Conformité :** RGPD à intégrer en phase 2 (chiffrement, droit à l'oubli, consentement)

---

## 2. Architecture Globale

```
[Caméras / Webcams]
        │ RTSP / USB
        ▼
[Agent Vidéo] ──── extraction frames ────▶ [Agent ML/IA]
                                                  │
                              détection + embedding (ArcFace 512d)
                                                  │
                                    ┌─────────────▼─────────────┐
                                    │   Moteur de matching       │
                                    │   (FAISS / Qdrant)         │
                                    └─────────────┬─────────────┘
                                                  │
                              ┌───────────────────┼───────────────────┐
                              │                   │                   │
                        [Autorisé]          [Inconnu/Intrus]    [Score faible]
                              │                   │                   │
                           Log audit        [Agent Sécurité]   [Active Learning]
                                            Alerte temps réel   File de review
                                                  │
                                          [Agent Backend]
                                         API REST + WebSocket
                                                  │
                                          [Agent Frontend]
                                        Dashboard + Alertes UI
```

---

## 3. Stack Technologique

### 3.1 Machine Learning
| Composant | Technologie | Justification |
|---|---|---|
| Framework ML | PyTorch 2.x | Flexibilité, support GPU, écosystème riche |
| Détection visages | InsightFace (RetinaFace) | SOTA précision, vitesse temps réel |
| Embeddings | ArcFace (buffalo_l) | Meilleur FAR/FRR du marché, embeddings 512d |
| Similarité | Cosine similarity | Invariant à l'échelle, standard biométrie |
| Vector DB local | FAISS | Recherche ANN ultra-rapide, 0 dépendance réseau |
| Vector DB VPS | Qdrant | Scalable, API REST, filtres métadonnées |
| Experiment tracking | MLflow | Suivi runs, métriques, versioning modèles |
| Active learning | Uncertainty sampling | Sélection auto des cas ambigus pour review |

### 3.2 Backend & API
| Composant | Technologie | Justification |
|---|---|---|
| API REST | FastAPI | Async natif, OpenAPI auto, performant |
| File de tâches | Celery + Redis | Entraînement async, non-bloquant |
| Base métadonnées | SQLite → PostgreSQL | SQLite local, migration transparente VPS |
| Temps réel | WebSocket (FastAPI) | Alertes push sans polling |
| Cache | Redis | Sessions, rate limiting, pub/sub alertes |

### 3.3 Traitement Vidéo
| Composant | Technologie | Justification |
|---|---|---|
| Capture flux | OpenCV 4.x | Standard industrie, support RTSP/USB |
| Transcodage | FFmpeg | Gestion codecs, réduction bitrate |
| Multi-caméras | Threading / GStreamer | Pipeline parallèle haute performance |

### 3.4 Infrastructure
| Composant | Technologie | Justification |
|---|---|---|
| Conteneurisation | Docker + Docker Compose | Reproductibilité local→VPS |
| Reverse proxy | Nginx | TLS termination, load balancing |
| Monitoring infra | Prometheus + Grafana | Métriques système, alertes bottleneck |
| Logs centralisés | Loki + Grafana | Corrélation logs/métriques |
| CI/CD | GitHub Actions | Automatisation tests et déploiement |

### 3.5 Frontend
| Composant | Technologie | Justification |
|---|---|---|
| Framework UI | React 18 | Écosystème, composants temps réel |
| Style | TailwindCSS | Rapidité de développement |
| Graphiques | Recharts | Léger, composants React natifs |
| Flux vidéo annoté | Canvas API + WebSocket | Overlay bounding boxes temps réel |

---

## 4. Fonctionnalités Détaillées

### 4.1 Enrôlement de profils
- Upload de N photos par personne (minimum 5, angles variés recommandés)
- Détection automatique et recadrage des visages à l'upload
- Génération et stockage de l'embedding moyen (centroïde des N embeddings)
- Association metadata : nom, rôle, plages horaires autorisées, date d'expiration
- Interface de validation manuelle avant activation du profil
- Possibilité de mise à jour / suppression complète d'un profil

### 4.2 Reconnaissance temps réel
- Cadence : 10–25 FPS selon résolution et matériel
- Détection multi-visages par frame
- Score de confiance par identification (cosine similarity → pourcentage)
- Seuils configurables : autorisé (>85%), suspect (70–85%), inconnu (<70%)
- Historique horodaté de chaque détection avec frame associée
- Support multi-caméras simultanées

### 4.3 Gestion des intrus
- Alerte instantanée via WebSocket → interface UI
- Capture et stockage de la frame incriminée
- Notification configurable (email, webhook, SMS)
- Tableau de bord des incidents avec timeline et filtres
- Possibilité d'enrôler rétroactivement un intrus comme profil autorisé

### 4.4 Auto-amélioration (Active Learning)
- Les détections avec score 70–85% sont mises en file de review
- Interface de labellisation humaine (confirmer / corriger l'identité)
- Déclenchement automatique du fine-tuning après N labels validés (configurable)
- Comparaison des métriques avant/après re-training (FAR, FRR, EER)
- Versioning automatique du modèle via MLflow avec rollback possible

---

## 5. Monitoring Avancé

### 5.1 Métriques ML
| Métrique | Description | Seuil d'alerte |
|---|---|---|
| FAR (False Acceptance Rate) | Intrus acceptés / total intrus | > 0.1% |
| FRR (False Rejection Rate) | Autorisés rejetés / total autorisés | > 1% |
| EER (Equal Error Rate) | Point d'équilibre FAR=FRR | Suivi par version modèle |
| Latence inférence | Temps embedding extraction | > 100ms |
| Score moyen confiance | Distribution des scores | Dérive > 5% |
| Drift détection | Comparaison distribution embeddings | Alerte si distribution shift |

### 5.2 Alertes Sécurité Réseau
- Détection de tentatives de connexion anormales à l'API (brute force, scan)
- Rate limiting par IP avec blacklist automatique après N tentatives
- Alertes sur accès aux endpoints sensibles hors plage horaire autorisée
- Détection d'injection dans les requêtes (SQLi, path traversal, XSS)
- Audit log chiffré de toutes les actions admin (RBAC, non-répudiation)
- Alerte si un flux caméra est interrompu (potentielle obstruction physique)
- Détection de tentatives de spoofing (photo / vidéo replay attack)

### 5.3 Anomalies Algorithmiques
- Détection de biais : baisse de performance sur sous-groupes (âge, conditions lumière, angle)
- Alerte si le taux de "non reconnu" augmente soudainement (signe de drift ou attaque)
- Remontée automatique des bugs d'inférence (NaN scores, dimensions incorrectes, crash worker)
- Rapport hebdomadaire automatique de santé du modèle (PDF généré)
- Détection de frames corrompues ou de résolution anormalement basse

### 5.4 Goulots de Performance
| Indicateur | Source | Seuil critique |
|---|---|---|
| CPU usage | Prometheus node_exporter | > 85% pendant 5min |
| GPU usage / VRAM | nvidia-smi exporter | VRAM > 90% |
| RAM usage | Prometheus | > 80% |
| Latence API (p99) | FastAPI middleware | > 500ms |
| Queue Celery | Redis | > 100 tâches en attente |
| FPS caméra effectif | Agent Vidéo | < 5 FPS |
| Temps recherche FAISS | Agent ML | > 50ms pour 100K vecteurs |
| I/O disque | Prometheus | > 80% saturation |

### 5.5 Dashboard de Monitoring
- Vue temps réel : flux vidéo annoté avec bounding boxes colorées
  - Vert = autorisé | Rouge = intrus | Orange = suspect
- Graphiques : évolution FAR/FRR, latences, scores de confiance, throughput
- Alertes triées par criticité avec acquittement opérateur
- Historique des incidents avec export PDF/CSV
- Vue santé système : CPU/GPU/RAM/réseau/disque
- Timeline des re-trainings et évolution des métriques ML par version
- Vue par caméra : statut, FPS effectif, dernière détection

---

## 6. Sécurité

### 6.1 Protection des données biométriques
- Embeddings chiffrés au repos (AES-256)
- Embeddings jamais exposés bruts via l'API (résultats uniquement)
- Stockage des images source séparé de la base de production
- Droit à l'oubli : suppression complète profil + embeddings + logs associés
- Pas de transfert d'embeddings en clair sur le réseau

### 6.2 Contrôle d'accès (RBAC)
| Rôle | Droits |
|---|---|
| Admin | Accès complet : enrôlement, suppression, configuration seuils, RBAC |
| Opérateur | Consultation alertes, acquittement incidents, review active learning |
| Viewer | Dashboard lecture seule, pas d'accès aux profils |
| Agent IA | API interne uniquement, token révocable, scope limité |

### 6.3 Communication
- HTTPS obligatoire (TLS 1.3 via Nginx)
- JWT pour authentification API avec expiration courte + refresh token
- Flux RTSP sur réseau interne uniquement (pas d'exposition externe)
- Secrets gérés via variables d'environnement (jamais en clair dans le code)

---

## 7. Infrastructure

### 7.1 Phase 1 — Local
```
Docker Compose :
├── api          (FastAPI — port 8000)
├── worker       (Celery — consommateur Redis)
├── redis        (Redis — broker + cache)
├── db           (SQLite via volume monté)
├── ml           (PyTorch + InsightFace — GPU passthrough)
├── video        (OpenCV workers — accès caméras)
├── frontend     (React build servi par Nginx — port 3000)
├── mlflow       (Tracking server — port 5000)
├── prometheus   (Métriques — port 9090)
└── grafana      (Dashboard infra — port 3001)
```
**Matériel minimum recommandé :** 16 Go RAM, GPU NVIDIA 8 Go VRAM (CUDA 11+), 500 Go SSD

### 7.2 Phase 2 — Migration VPS
- SQLite → PostgreSQL (service dédié ou managed)
- FAISS → Qdrant (service dédié avec persistance)
- Nginx reverse proxy public avec Let's Encrypt (HTTPS automatique)
- GitHub Actions pour CI/CD automatisé (tests + build + deploy)
- Volumes persistants pour modèles MLflow et données biométriques
- Scaling horizontal des workers Celery selon charge GPU/CPU

---

## 8. Métriques d'Évaluation

| Métrique | Formule | Objectif |
|---|---|---|
| FAR | FP / (FP + TN) | < 0.1% |
| FRR | FN / (FN + TP) | < 1% |
| TAR@FAR=0.1% | TP rate à FAR fixé | > 99% |
| EER | Point où FAR = FRR | < 0.5% |
| Latence P95 | 95e percentile temps inférence | < 80ms |
| Throughput | Identifications / seconde / caméra | > 10/s |

---

## 9. Roadmap

### Phase 1 — MVP Local (Semaines 1–4)
- [ ] Pipeline détection + embedding fonctionnel (InsightFace + ArcFace)
- [ ] Base de données profils (SQLite + FAISS)
- [ ] API REST de base (enrôlement, identification, suppression)
- [ ] Interface d'enrôlement multi-photos
- [ ] Intégration flux webcam USB

### Phase 2 — Temps réel & Alertes (Semaines 5–8)
- [ ] Ingestion flux RTSP multi-caméras
- [ ] Système d'alertes WebSocket temps réel
- [ ] Dashboard React avec flux annoté (bounding boxes)
- [ ] RBAC et authentification JWT
- [ ] Monitoring Prometheus + Grafana

### Phase 3 — Active Learning & Monitoring Avancé (Semaines 9–12)
- [ ] Pipeline active learning + interface de review
- [ ] Détection de drift et anomalies algorithmiques
- [ ] Alertes sécurité réseau automatisées
- [ ] Rapports automatiques de santé modèle (PDF)
- [ ] Export incidents PDF/CSV

### Phase 4 — Migration VPS & Scalabilité (Semaines 13–16)
- [ ] Migration PostgreSQL + Qdrant
- [ ] CI/CD GitHub Actions
- [ ] TLS production (Let's Encrypt + Nginx)
- [ ] Scaling horizontal workers Celery
- [ ] Audit sécurité complet + tests de charge
