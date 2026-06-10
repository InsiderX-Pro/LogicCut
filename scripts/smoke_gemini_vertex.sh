#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/env.sh
source "${ROOT_DIR}/scripts/env.sh"

if [[ -z "${GEMINI_CREDENTIALS_JSON:-}" ]]; then
  echo "GEMINI_CREDENTIALS_JSON is required. Put it in .env.local." >&2
  exit 1
fi

"${LOGICCUT_VENV}/bin/python" - <<'PY'
import json
import os
from pathlib import Path

import vertexai
from vertexai.generative_models import GenerationConfig, GenerativeModel

credentials = Path(os.environ["GEMINI_CREDENTIALS_JSON"]).expanduser().resolve()
data = json.loads(credentials.read_text(encoding="utf-8"))
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials)
location = os.environ.get("GEMINI_VERTEX_LOCATION", "us-central1")
model_name = os.environ.get("LOGICCUT_GEMINI_MODEL", "gemini-2.5-pro")
vertexai.init(project=data.get("project_id"), location=location)
model = GenerativeModel(model_name)
response = model.generate_content(
    'Return JSON only: {"ok": true, "module": "logiccut-gemini-smoke"}',
    generation_config=GenerationConfig(response_mime_type="application/json", temperature=0, max_output_tokens=128),
)
parsed = json.loads(response.text)
print(json.dumps({
    "gemini_vertex_ready": True,
    "credentials_json_exists": credentials.exists(),
    "project_id_present": bool(data.get("project_id")),
    "client_email_present": bool(data.get("client_email")),
    "location": location,
    "model": model_name,
    "generation_ok": parsed.get("ok") is True,
}, ensure_ascii=False, indent=2))
PY
