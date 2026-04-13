# Agent Frontend — Instructions

**Rôle :** Dashboard de monitoring temps réel, gestion des profils autorisés, visualisation des alertes et interface de review active learning.

---

## 1. Responsabilités

- Afficher les flux vidéo annotés en temps réel (bounding boxes, identités, scores)
- Présenter les alertes et incidents avec gestion opérateur
- Exposer les métriques ML et système sous forme de graphiques
- Fournir l'interface d'enrôlement de profils (multi-photos)
- Fournir l'interface de review active learning (labellisation)
- Gérer l'authentification et les permissions RBAC côté UI

---

## 2. Stack technique

| Outil | Usage |
|---|---|
| React 18 | Framework UI |
| TailwindCSS 3.x | Styles utilitaires |
| Recharts | Graphiques métriques |
| Canvas API | Overlay bounding boxes sur flux vidéo |
| WebSocket (natif) | Alertes et métriques temps réel |
| React Query | Fetching, cache et synchronisation API |
| React Router 6 | Navigation SPA |
| Zustand | State management global (alertes, session) |
| date-fns | Formatage dates/heures |

---

## 3. Pages et vues

### 3.1 Dashboard principal (`/`)
**Accessible à tous les rôles.**
- Grille de flux vidéo annotés (1 à N caméras, layout configurable)
- Compteur temps réel : autorisés / suspects / intrus détectés aujourd'hui
- Alerte banner pour les incidents non acquittés
- Indicateurs santé système (CPU/GPU/RAM — barres de progression colorées)
- Mini-graphique FAR/FRR sur les 24 dernières heures

### 3.2 Flux vidéo annoté (Canvas)
Pour chaque caméra :
- Stream MJPEG ou frames via WebSocket
- Overlay Canvas :
  - **Vert** : bounding box + nom + score (ex: "Jean Dupont — 94%")
  - **Orange** : bounding box + "Suspect — 76%"
  - **Rouge** : bounding box + "INTRUS" + animation clignotante
- FPS effectif affiché en overlay
- Statut caméra (actif / coupé / dégradé)

### 3.3 Alertes & Incidents (`/alerts`)
**Accessible : Admin, Opérateur.**
- Liste des alertes triées par criticité et date
- Filtres : niveau (WARNING/ALERT/CRITICAL), caméra, plage de dates, statut (acquitté/non acquitté)
- Détail alerte : frame capturée, score, caméra, timestamp, historique actions
- Bouton acquittement avec note opérateur obligatoire
- Export CSV / PDF de la sélection

### 3.4 Gestion des profils (`/profiles`)
**Accessible : Admin uniquement.**
- Liste des profils autorisés (photo principale, nom, rôle, statut actif/expiré)
- Création de profil :
  1. Formulaire : nom, rôle, plages horaires, date d'expiration
  2. Upload multi-photos (drag & drop, prévisualisation, indicateur qualité par image)
  3. Validation manuelle avant activation
- Modification : ajout de photos, mise à jour métadonnées
- Suppression : confirmation en deux étapes + mention RGPD

### 3.5 Review Active Learning (`/review`)
**Accessible : Admin, Opérateur.**
- File de frames à labelliser (triée par score d'incertitude croissant)
- Pour chaque frame :
  - Image affichée en grand
  - Candidats proposés avec scores (boutons de confirmation rapide)
  - Sélecteur de profil complet si le bon candidat n'est pas dans la liste
  - Options : Confirmer / Corriger / Nouveau profil / Intrus / Rejeter
- Compteur de progression : N frames labellisées / N total
- Indicateur : "Fine-tuning se déclenchera dans X labels"

### 3.6 Monitoring ML (`/monitoring/ml`)
**Accessible : Admin.**
- Graphiques temporels : FAR, FRR, EER (par version modèle)
- Distribution des scores de confiance (histogramme)
- Score de drift dans le temps
- Timeline des entraînements avec delta métriques (avant/après)
- Historique des versions modèles avec possibilité de rollback
- Bouton "Déclencher fine-tuning manuel"

### 3.7 Monitoring Système (`/monitoring/system`)
**Accessible : Admin.**
- Graphiques temps réel : CPU, RAM, GPU VRAM, disque, réseau
- Statut de tous les services Docker (api, worker, ml, video, redis...)
- Alertes bottleneck actives
- Logs récents (niveau ERROR et CRITICAL) avec lien vers Grafana
- Statut de chaque caméra : FPS, résolution, dernière frame, connexion

### 3.8 Paramètres (`/settings`)
**Accessible : Admin uniquement.**
- Configuration des seuils (autorisé / suspect / inconnu)
- Configuration des notifications (email, webhook, SMS)
- Gestion des utilisateurs et rôles (RBAC)
- Configuration des caméras (ajout, modification, suppression)
- Paramètres active learning (seuil déclenchement fine-tuning)

---

## 4. Gestion des WebSockets

```javascript
// Connexions WebSocket maintenues en permanence
const wsAlerts  = new WebSocket('/ws/alerts');      // Alertes toutes caméras
const wsMetrics = new WebSocket('/ws/metrics');     // CPU/GPU/RAM temps réel
const wsCamera  = new WebSocket('/ws/cameras/X');  // Frames caméra X

// Reconnexion automatique avec backoff exponentiel
// Indicateur visuel de connexion (point vert/rouge en header)
```

---

## 5. UX / Design

- **Thème** : dark mode par défaut (interface surveillance, ambiance salle de contrôle)
- **Palette** :
  - Vert `#22c55e` : autorisé, OK
  - Orange `#f97316` : suspect, warning
  - Rouge `#ef4444` : intrus, critique
  - Bleu `#3b82f6` : info, neutre
  - Gris sombre `#111827` : fond
- **Responsive** : optimisé grand écran (1920x1080) mais utilisable en 1280x768
- **Actualisation** : métriques toutes les 5s, alertes en temps réel, flux vidéo continu
- **Accessibilité** : contrastes WCAG AA minimum, navigation clavier sur les actions critiques

---

## 6. Sécurité Frontend

- Token JWT stocké en mémoire uniquement (jamais localStorage)
- Refresh token via cookie httpOnly (géré par le backend)
- Routes protégées par rôle (redirect si permission insuffisante)
- Pas de données biométriques affichées (noms et scores uniquement)
- Content Security Policy (CSP) stricte configurée dans Nginx
- Timeout de session automatique après 30 min d'inactivité
