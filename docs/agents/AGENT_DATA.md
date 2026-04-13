# Agent Data — Instructions

**Rôle :** Gestion du dataset, annotation, augmentation des données, versioning et qualité des données d'entraînement.

---

## 1. Responsabilités

- Maintenir et versionner le dataset d'entraînement et de validation
- Gérer l'interface d'annotation (active learning review)
- Appliquer les pipelines d'augmentation pour enrichir le dataset
- Contrôler la qualité des données (doublons, images corrompues, biais)
- Assurer la traçabilité des données (lineage) de la source au modèle entraîné
- Gérer les exports et imports de datasets

---

## 2. Stack technique

| Outil | Usage |
|---|---|
| DVC (Data Version Control) | Versioning datasets et modèles |
| Albumentations | Augmentation d'images |
| Label Studio (optionnel) | Interface annotation externe |
| Pillow / OpenCV | Manipulation images |
| Pandas | Analyse et nettoyage métadonnées |
| SQLite / PostgreSQL | Catalogue des données |

---

## 3. Structure des données

```
data/
├── raw/                    # Images sources originales (non modifiées)
│   ├── profiles/
│   │   ├── {profile_id}/
│   │   │   ├── img_001.jpg
│   │   │   ├── img_002.jpg
│   │   │   └── metadata.json
│   └── unknown/            # Frames intrus stockées
│
├── processed/              # Images prétraitées (alignées, recadrées 112x112)
│   └── profiles/
│       └── {profile_id}/
│
├── active_learning/        # Frames en attente de labellisation
│   ├── pending/
│   └── labeled/
│
├── train/                  # Dataset entraînement (après split)
├── val/                    # Dataset validation
└── test/                   # Dataset test (ne jamais utiliser pour training)
```

---

## 4. Pipeline d'ingestion d'un nouveau profil

```
Images uploadées (N images)
        │
        ▼
[Validation qualité]
  - Format accepté (JPEG/PNG/WEBP)
  - Résolution minimum (160x160)
  - Détection visage obligatoire (RetinaFace)
  - Rejet si flou > seuil ou luminosité hors range
        │
        ▼
[Déduplication]
  - Hash perceptuel (pHash) pour détecter doublons visuels
  - Alerte si > 2 images trop similaires dans le même upload
        │
        ▼
[Prétraitement]
  - Alignement facial (landmarks RetinaFace)
  - Recadrage 112x112px
  - Normalisation pixel [0,1]
        │
        ▼
[Stockage]
  - raw/ : image originale conservée
  - processed/ : image prétraitée stockée
  - Métadonnées enregistrées en base
        │
        ▼
[Versioning DVC]
  - Commit DVC après chaque ajout de profil
  - Tag de version du dataset
```

---

## 5. Augmentation de données

Appliquée uniquement lors de l'entraînement (pas sur les données de prod) :

```python
# Pipeline Albumentations recommandé
transforms = [
    RandomBrightnessContrast(p=0.5),      # Variations lumière
    HorizontalFlip(p=0.5),                 # Symétrie
    Rotate(limit=15, p=0.5),              # Légère rotation
    GaussianBlur(blur_limit=3, p=0.3),    # Simulation flou caméra
    RandomShadow(p=0.3),                  # Simulation ombre partielle
    ColorJitter(p=0.4),                   # Variation couleur/teinte
    CoarseDropout(p=0.2),                 # Simulation occlusion partielle
]
```

Ne pas appliquer :
- Flips verticaux (dénature le visage)
- Rotations > 30° (hors distribution réelle)
- Transformations qui masquent > 50% du visage

---

## 6. Contrôle qualité du dataset

### 6.1 Métriques de qualité surveillées
| Métrique | Seuil d'alerte |
|---|---|
| Images par profil | < 5 images → WARNING |
| Distribution des angles | < 3 angles différents → WARNING |
| Score de netteté moyen | < seuil Laplacien → WARNING |
| Ratio train/val/test | Doit être 80/10/10 |
| Déséquilibre de classes | Ratio max/min profiles > 10x → WARNING |

### 6.2 Détection de biais
- Surveiller les performances par sous-groupe (si metadata disponible)
- Alerter si un profil a un FRR significativement plus élevé que la moyenne
- Recommander l'ajout de photos supplémentaires pour les profils sous-représentés

---

## 7. Versioning avec DVC

```bash
# Après ajout d'un nouveau profil
dvc add data/raw/profiles/
git add data/raw/profiles/.dvc
git commit -m "data: ajout profil {nom} ({N} images)"
dvc push  # vers stockage distant (S3, GCS, local NAS)

# Après re-training
dvc add models/
git tag -a "model-v{X}" -m "Model version {X} — FAR:{FAR} FRR:{FRR}"
```

Chaque run MLflow est lié au hash DVC du dataset utilisé pour la traçabilité complète.

---

## 8. Active Learning — Interface de labellisation

### 8.1 Format d'une tâche de review
```json
{
  "review_id": "uuid",
  "frame_path": "/active_learning/pending/uuid.jpg",
  "camera_id": "cam_entree",
  "timestamp": "2026-04-13T10:23:45Z",
  "confidence_score": 0.74,
  "top_candidates": [
    {"profile_id": "abc", "name": "Jean Dupont", "score": 0.74},
    {"profile_id": "def", "name": "Marie Martin", "score": 0.61}
  ],
  "status": "pending"
}
```

### 8.2 Actions possibles pour l'opérateur
- **Confirmer** un candidat proposé
- **Corriger** en sélectionnant le bon profil dans la liste
- **Créer un nouveau profil** (personne inconnue autorisée à ajouter)
- **Marquer comme intrus** (confirmer alerte)
- **Rejeter** (frame de mauvaise qualité, non exploitable)

---

## 9. Droit à l'oubli (RGPD)

Procédure de suppression complète d'un profil :
1. Supprimer `data/raw/profiles/{profile_id}/`
2. Supprimer `data/processed/profiles/{profile_id}/`
3. Supprimer toutes les frames active learning liées
4. Supprimer embedding FAISS/Qdrant
5. Anonymiser les logs d'audit (remplacer nom par hash irréversible)
6. Committer la suppression dans DVC
7. Générer certificat de suppression horodaté
