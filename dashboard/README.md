# dashboard – Streamlit user interface

**Filled in:** Phase 15 (Data Upload page from Phase 4).

The dashboard imports the same `app/services` as the API, so numbers always match Swagger.

| Planned page (`pages/`) | Shows |
| --- | --- |
| `Home.py` | Totals and summaries |
| `1_Data_Upload.py` | CSV upload, preview, validation, status |
| `2_Skills_Analysis.py` | One employee's gaps for a target role |
| `3_Role_Matching.py` | Roles ranked by match % |
| `4_Recommendations.py` | Courses with reasons |
| `5_Learning_Path.py` | Ordered courses and progress |
| `6_AI_Assistant.py` | Chat with sources |
| `7_Document_Management.py` | Upload, list and delete knowledge documents (admin) |
| `8_Model_Management.py` | Model versions, metrics, retraining (admin) |

`components/` holds reusable charts and tables.

Run (later): `streamlit run dashboard/Home.py`
