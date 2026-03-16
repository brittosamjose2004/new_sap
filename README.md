# new_sap

Process documentation: [PROCESS_DOCUMENTATION.md](./PROCESS_DOCUMENTATION.md)

Run locally:

```bash
# backend
cd /workspaces/new_sap
python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000

# frontend
cd /workspaces/new_sap/rubicr-caetis---super-admin
npm run dev -- --host 0.0.0.0 --port 3000
```