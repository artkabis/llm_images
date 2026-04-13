# Facial Recognition System — Vidéosurveillance d'Entreprise

Système de reconnaissance faciale temps réel pour la sécurité des accès en entreprise.

## Objectif
Détecter automatiquement les personnes autorisées et les intrus sur des flux vidéo multi-caméras, avec alertes temps réel et tableau de bord de monitoring avancé.

## Documentation
| Document | Description |
|---|---|
| [Cahier des charges](CAHIER_DES_CHARGES.md) | Spécification complète du système |
| [Agent ML/IA](docs/agents/AGENT_ML_IA.md) | Instructions entraînement & embeddings |
| [Agent Vidéo](docs/agents/AGENT_VIDEO.md) | Instructions traitement flux vidéo |
| [Agent Sécurité](docs/agents/AGENT_SECURITE.md) | Instructions détection & alertes |
| [Agent Backend](docs/agents/AGENT_BACKEND.md) | Instructions API & orchestration |
| [Agent Infra](docs/agents/AGENT_INFRA.md) | Instructions infrastructure & déploiement |
| [Agent Data](docs/agents/AGENT_DATA.md) | Instructions dataset & annotation |
| [Agent Frontend](docs/agents/AGENT_FRONTEND.md) | Instructions dashboard & UI |

## Stack
- **ML** : Python · PyTorch · InsightFace · ArcFace
- **API** : FastAPI · Celery · Redis
- **Vidéo** : OpenCV · FFmpeg
- **Stockage** : SQLite→PostgreSQL · FAISS→Qdrant
- **Monitoring** : MLflow · Prometheus · Grafana
- **Infra** : Docker Compose → VPS
- **UI** : React · TailwindCSS · Recharts
