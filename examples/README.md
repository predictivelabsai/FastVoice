# FastVoice examples

Supported runnable examples are in [`python/`](python):

- `create_workflow.py` creates an agent from a graph definition;
- `build_workflow_with_sdk.py` builds a typed workflow and saves a draft;
- `load_and_edit_workflow.py` loads and changes an existing workflow;
- `fetch_workflow_and_call.py` places an outbound test call.

```bash
cd examples/python
cp .env.example .env
uv pip install -r requirements.txt
python create_workflow.py
```

Set `FASTVOICE_API_ENDPOINT` and `FASTVOICE_API_TOKEN` in the ignored `.env`.
