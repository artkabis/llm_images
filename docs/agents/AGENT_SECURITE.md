# Agent Sécurité — Instructions

**Rôle :** Détection des intrus, gestion des alertes temps réel, audit trail, contrôle d'accès (RBAC) et surveillance réseau.

---

## 1. Responsabilités

- Recevoir et traiter les événements de détection (autorisé / suspect / intrus)
- Émettre des alertes temps réel via WebSocket et notifications externes
- Maintenir l'audit log chiffré de toutes les actions système
- Surveiller le trafic réseau et les tentatives d'accès anormales
- Gérer les blacklists/whitelists IP et les sessions utilisateurs
- Détecter les tentatives de spoofing (photo/vidéo replay attack)

---

## 2. Stack technique

| Outil | Usage |
|---|---|
| Redis Pub/Sub | Bus d'événements temps réel inter-agents |
| WebSocket (FastAPI) | Diffusion alertes vers le frontend |
| JWT + Redis | Gestion sessions et tokens révocables |
| AES-256 (cryptography lib) | Chiffrement audit logs et embeddings |
| Prometheus | Exposition métriques sécurité |
| SMTP / Webhook / SMS API | Notifications externes configurables |

---

## 3. Niveaux d'alerte

| Niveau | Couleur | Déclencheur | Action automatique |
|---|---|---|---|
| INFO | Bleu | Personne autorisée détectée | Log audit uniquement |
| WARNING | Orange | Score 70–85% (suspect) | Log + file active learning |
| ALERT | Rouge | Personne non reconnue (<70%) | Log + notification opérateur + capture frame |
| CRITICAL | Rouge clignotant | Flux caméra coupé / spoofing détecté | Log + notification d'urgence + escalade |

---

## 4. Pipeline de traitement des alertes

```
Événement reçu (Redis Pub/Sub)
        │
        ▼
[Classifieur d'alertes] ── Niveau INFO / WARNING / ALERT / CRITICAL
        │
        ├── INFO ──▶ Audit log uniquement
        │
        ├── WARNING ──▶ Audit log + Redis queue active learning
        │
        ├── ALERT ──▶ Audit log + WebSocket push + Capture frame stockée
        │               + Notification (email/webhook/SMS selon config)
        │
        └── CRITICAL ──▶ Tout ci-dessus + Escalade superviseur
                          + Blocage accès si intégration contrôle physique
```

---

## 5. Audit Log

### 5.1 Format d'un événement
```json
{
  "event_id": "uuid-v4",
  "timestamp": "2026-04-13T10:23:45.123Z",
  "camera_id": "cam_entree_principale",
  "event_type": "INTRUDER_DETECTED",
  "level": "ALERT",
  "confidence_score": 0.42,
  "matched_profile_id": null,
  "frame_path": "/secure/captures/2026-04-13/uuid.jpg.enc",
  "operator_id": null,
  "ip_source": null,
  "signature": "HMAC-SHA256-de-l-evenement"
}
```

### 5.2 Propriétés de l'audit log
- Stocké en append-only (jamais modifié, jamais supprimé sauf droit à l'oubli)
- Chiffré par batch quotidien (AES-256)
- Signé avec HMAC-SHA256 (non-répudiation)
- Rotation des clés de chiffrement mensuelle
- Rétention configurable (défaut : 90 jours)

---

## 6. Surveillance réseau

### 6.1 Détection d'anomalies
- Rate limiting par IP : max 100 req/min sur l'API publique
- Blacklist automatique après 10 tentatives d'authentification échouées en 5 min
- Alerte si endpoint admin accédé hors plage horaire configurée
- Scan de ports détecté → alerte CRITICAL + log IP

### 6.2 Détection d'injection
- Validation stricte de tous les inputs (Pydantic + regex)
- Détection patterns SQLi / path traversal / XSS dans les champs libres
- Blocage immédiat de la requête + log + alerte si pattern détecté

### 6.3 Surveillance des flux caméras
- Ping heartbeat chaque 5s vers chaque caméra
- Coupure > 10s → ALERT
- Image statique > 30s → ALERT (obstruction potentielle)
- Baisse brutale qualité → WARNING

---

## 7. Détection de spoofing

Techniques de détection à implémenter progressivement :
- **Liveness detection (passive)** : analyse texture peau, reflets, micro-mouvements
- **Détection photo** : vérifier absence de bordures de cadre, planéité excessive
- **Détection vidéo replay** : comparer avec frames précédentes, détecter boucle
- Si spoofing détecté → CRITICAL + capture + blacklist temporaire zone

---

## 8. Gestion RBAC

### 8.1 Rôles et permissions
| Rôle | Enrôlement | Suppression profil | Config seuils | Audit log | Alertes | Dashboard |
|---|---|---|---|---|---|---|
| Admin | ✅ | ✅ | ✅ | ✅ complet | ✅ | ✅ |
| Opérateur | ❌ | ❌ | ❌ | ✅ lecture | ✅ acquittement | ✅ |
| Viewer | ❌ | ❌ | ❌ | ❌ | ✅ lecture | ✅ lecture |
| Agent IA | API interne | scope limité | ❌ | ❌ | ❌ | ❌ |

### 8.2 Gestion des tokens
- JWT avec expiration courte (15 min) + refresh token (7 jours)
- Refresh tokens stockés dans Redis (révocation immédiate possible)
- Token révoqué automatiquement en cas d'activité suspecte détectée

---

## 9. Métriques exposées

| Métrique | Type | Description |
|---|---|---|
| `security_alerts_total` | Counter | Total alertes par niveau |
| `security_intruders_detected` | Counter | Intrus détectés |
| `security_api_blocked_ips` | Gauge | IPs actuellement blacklistées |
| `security_failed_auth_attempts` | Counter | Tentatives auth échouées |
| `security_spoofing_attempts` | Counter | Tentatives de spoofing détectées |
| `security_audit_log_size_bytes` | Gauge | Taille audit log chiffré |

---

## 10. Notifications externes

Configuration via variables d'environnement :
```env
NOTIFY_EMAIL_ENABLED=true
NOTIFY_EMAIL_RECIPIENTS=security@entreprise.com,admin@entreprise.com
NOTIFY_WEBHOOK_URL=https://hooks.slack.com/...
NOTIFY_SMS_ENABLED=false
NOTIFY_MIN_LEVEL=ALERT  # INFO / WARNING / ALERT / CRITICAL
```
