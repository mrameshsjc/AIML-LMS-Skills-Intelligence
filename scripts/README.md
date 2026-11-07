# scripts – helper scripts

| Script | Purpose | Phase |
| --- | --- | --- |
| `verify_phase1.py` | Checks your setup, starts the API, calls the health endpoint and runs the tests | 1 – **done** |
| `generate_synthetic_data.py` | Creates the 11 synthetic CSV files in `data/sample` | 2 – **done** |
| `make_dirty_data.py` | Copies `data/sample` to `data/raw/dirty` with 17 planted defects for practising validation | 3 – **done** |
| `reset_demo_data.py` | Restores demo data for the public demo | 19 |
