# Agent ML/IA — Instructions

**Rôle :** Responsable de l'entraînement, du fine-tuning, de la gestion des embeddings et de l'active learning.

---

## 1. Responsabilités

- Maintenir le pipeline de détection et d'extraction d'embeddings faciaux
- Gérer le cycle de vie des modèles (entraînement, versioning, déploiement, rollback)
- Implémenter et superviser l'active learning
- Détecter et alerter sur les dérives du modèle (drift)
- Exposer les métriques ML à Prometheus et MLflow

---

## 2. Stack technique

| Outil | Version | Usage |
|---|---|---|
| Python | 3.11+ | Langage principal |
| PyTorch | 2.x | Framework deep learning |
| InsightFace | 0.7+ | Détection (RetinaFace) + embeddings (ArcFace buffalo_l) |
| FAISS | 1.7+ | Index vectoriel local (phase 1) |
| Qdrant | 1.x | Index vectoriel distribué (phase 2) |
| MLflow | 2.x | Tracking expériences, versioning modèles |
| NumPy / SciPy | latest | Calculs vectoriels, similarité cosinus |
| Albumentations | latest | Augmentation données à l'entraînement |

---

## 3. Pipeline d'inférence

```
Frame reçue de l'Agent Vidéo
        │
        ▼
[RetinaFace] ── Détection visages ──▶ Bounding boxes + landmarks
        │
        ▼
[Alignement facial] ── Normalisation 112x112px
        │
        ▼
[ArcFace buffalo_l] ── Extraction embedding 512d
        │
        ▼
[FAISS / Qdrant] ── Recherche ANN (top-k=5)
        │
        ▼
[Score cosinus] ── Calcul similarité avec profils candidats
        │
        ▼
[Décision] ── Autorisé / Suspect / Inconnu selon seuils
```

---

## 4. Gestion des embeddings

### 4.1 Enrôlement d'un profil
1. Recevoir N images (minimum 5, angles variés)
2. Détecter et aligner chaque visage (RetinaFace)
3. Extraire les N embeddings (ArcFace)
4. Calculer le centroïde : `embedding_moyen = mean(embeddings)`
5. Stocker dans FAISS/Qdrant avec metadata (id_profil, nom, rôle, date)
6. Persister le mapping id_profil → metadata en base (SQLite/PostgreSQL)

### 4.2 Mise à jour d'un profil
- Ajouter de nouvelles images → recalculer le centroïde
- Incrémenter la version du profil dans MLflow
- Ne jamais supprimer l'ancien embedding sans validation opérateur

### 4.3 Suppression d'un profil
- Supprimer le vecteur de FAISS/Qdrant
- Supprimer les images source
- Purger les logs associés (droit à l'oubli)
- Enregistrer l'événement dans l'audit log

---

## 5. Active Learning

### 5.1 Critères de sélection
Les frames sont envoyées en file de review si :
- Score cosinus entre **0.70 et 0.85** (zone d'incertitude)
- Aucun top-k candidat avec score > 0.85
- Score le plus élevé < 0.70 mais visage détecté clairement

### 5.2 Workflow de review
1. Frame incertaine stockée avec metadata (timestamp, caméra, score, candidat probable)
2. Opérateur accède à l'interface de labellisation (Agent Frontend)
3. Opérateur confirme ou corrige l'identité
4. Label validé ajouté au dataset de fine-tuning
5. Déclenchement du fine-tuning si `N_labels >= seuil_configurable` (défaut : 50)

### 5.3 Fine-tuning
- Loss : ArcFace loss (margin=0.5, scale=64)
- Optimiseur : SGD + momentum ou AdamW
- Learning rate : 1e-4 (fine-tuning layers finaux uniquement)
- Validation : métriques FAR/FRR sur jeu de test séparé
- Si métriques améliorées → déploiement automatique
- Si dégradation → rollback vers version précédente MLflow
- Toujours versionner le modèle avant remplacement

---

## 6. Détection de dérive (Drift)

- Calculer la distribution des scores de confiance sur fenêtre glissante (1h)
- Alerter si la moyenne glissante baisse de > 5% par rapport à la baseline
- Calculer et stocker la distribution des embeddings (PCA 2D) par batch
- Détecter les shifts de distribution avec test statistique (MMD ou KS test)
- Logger toutes les anomalies dans MLflow et envoyer alerte à l'Agent Sécurité

---

## 7. Métriques exposées

| Métrique | Type | Description |
|---|---|---|
| `ml_inference_latency_ms` | Histogram | Temps d'extraction embedding |
| `ml_confidence_score` | Gauge | Score moyen sur fenêtre glissante |
| `ml_far` | Gauge | False Acceptance Rate courant |
| `ml_frr` | Gauge | False Rejection Rate courant |
| `ml_active_learning_queue` | Gauge | Nombre de frames en attente de review |
| `ml_model_version` | Gauge | Version du modèle actif |
| `ml_drift_score` | Gauge | Score de dérive de distribution |

---

## 8. Protocoles de sécurité

- Ne jamais logger les embeddings bruts en clair
- Chiffrer les embeddings stockés (AES-256)
- Valider les dimensions d'entrée avant inférence (assertion 512d)
- Gérer les exceptions GPU (OOM) avec fallback CPU et alerte
- Timeout d'inférence : max 200ms par frame (sinon skip + log)
