# deployment/cloud (Phase 19)

| Path | Use |
| --- | --- |
| `huggingface/README.dashboard.md`, `huggingface/README.api.md` | The text shown on each Hugging Face Space page |

The Space folders are generated, not stored here:

```powershell
python scripts/prepare_hf_space.py dashboard --out ..\hf-lms-dashboard
python scripts/prepare_hf_space.py api --out ..\hf-lms-api
```

Step-by-step deployment: `docs/PUBLIC_DEPLOYMENT_GUIDE.md`.
