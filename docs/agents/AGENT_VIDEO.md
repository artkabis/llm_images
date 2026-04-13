# Agent Vidéo — Instructions

**Rôle :** Ingestion et prétraitement des flux vidéo multi-caméras, extraction de frames, transmission à l'Agent ML/IA.

---

## 1. Responsabilités

- Connecter et maintenir les flux vidéo (webcams USB, caméras IP RTSP)
- Extraire les frames à la cadence optimale
- Prétraiter les frames (redimensionnement, normalisation, filtre qualité)
- Détecter les anomalies de flux (coupure, obstruction, dégradation qualité)
- Exposer les métriques de flux à Prometheus

---

## 2. Stack technique

| Outil | Usage |
|---|---|
| OpenCV 4.x | Capture flux, traitement image |
| FFmpeg | Transcodage, gestion codecs, extraction HLS |
| GStreamer (optionnel) | Pipeline multi-caméras haute performance |
| Redis | Queue de frames vers Agent ML/IA |
| Threading / asyncio | Parallélisme multi-caméras |

---

## 3. Architecture multi-caméras

```
[Caméra 1 RTSP] ──▶ [Worker Thread 1] ──▶ Redis Queue ──▶ Agent ML/IA
[Caméra 2 RTSP] ──▶ [Worker Thread 2] ──▶ Redis Queue
[Webcam USB]    ──▶ [Worker Thread 3] ──▶ Redis Queue
        │
        ▼
[Health Monitor] ── Vérifie FPS, qualité, connectivité toutes les 5s
        │
        ▼
[Prometheus] ── Métriques par caméra
```

---

## 4. Pipeline de traitement des frames

### 4.1 Extraction
- Lecture frame depuis le flux (`cv2.VideoCapture`)
- Cadence cible : 10–25 FPS (configurable par caméra)
- Stratégie de sous-échantillonnage : traiter 1 frame sur N si charge élevée
- Timestamping précis à l'acquisition (UTC)

### 4.2 Contrôle qualité
Rejeter une frame si :
- Résolution < seuil minimum configuré (défaut : 320x240)
- Flou détecté (variance Laplacien < seuil)
- Luminosité moyenne < 20 ou > 240 (sur-exposition / sous-exposition)
- Frame identique à la précédente (diff pixel < 0.1%)

### 4.3 Prétraitement
1. Redimensionnement si nécessaire (max 1280px largeur)
2. Conversion BGR → RGB
3. Encodage JPEG qualité 85% pour transmission Redis
4. Ajout metadata : `{camera_id, timestamp, frame_id, resolution}`

---

## 5. Gestion des connexions

### 5.1 Reconnexion automatique
- En cas de coupure : tentative de reconnexion avec backoff exponentiel
  - Tentative 1 : après 2s
  - Tentative 2 : après 4s
  - Tentative 3+ : après 8s (max)
- Après 3 échecs consécutifs → alerte critique envoyée à l'Agent Sécurité
- Log de chaque coupure avec durée d'indisponibilité

### 5.2 Détection d'obstruction
- Comparer histogramme couleur sur fenêtre de 10s
- Si variance < seuil (image statique / caméra obstruée) → alerte orange
- Si flux noir complet > 3s → alerte rouge (coupure intentionnelle potentielle)

### 5.3 Configuration par caméra
```yaml
cameras:
  - id: cam_entree_principale
    type: rtsp
    url: rtsp://192.168.1.100:554/stream
    fps_target: 15
    resolution_min: [640, 480]
    zone: "Entrée principale"
    
  - id: cam_parking
    type: rtsp
    url: rtsp://192.168.1.101:554/stream
    fps_target: 10
    resolution_min: [320, 240]
    zone: "Parking"
    
  - id: webcam_bureau
    type: usb
    device_id: 0
    fps_target: 25
    zone: "Bureau direction"
```

---

## 6. Métriques exposées

| Métrique | Type | Description |
|---|---|---|
| `video_fps_effective` | Gauge | FPS réel par caméra |
| `video_frames_dropped` | Counter | Frames rejetées (qualité) |
| `video_stream_status` | Gauge | 1=actif, 0=coupé, 2=dégradé |
| `video_queue_size` | Gauge | Taille queue Redis vers ML |
| `video_reconnect_count` | Counter | Nombre de reconnexions |
| `video_blur_score` | Gauge | Score de netteté moyen |

---

## 7. Protocoles de sécurité

- URLs RTSP stockées en variables d'environnement (jamais en dur dans le code)
- Authentification RTSP via credentials chiffrés
- Pas de stockage permanent des frames brutes (sauf incidents)
- Accès caméras sur réseau VLAN interne uniquement
