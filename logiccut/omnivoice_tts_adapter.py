from __future__ import annotations

import argparse
import json
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable


PostJson = Callable[[str, dict[str, Any]], bytes]


class OmniVoiceTtsAdapter:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:3900",
        model: str = "omnivoice",
        voice: str = "default",
        timeout_s: int = 300,
        post_json: Callable[..., bytes] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.voice = voice
        self.timeout_s = timeout_s
        self._post_json = post_json or post_json_bytes

    def health(self) -> dict[str, Any]:
        with urllib.request.urlopen(f"{self.base_url}/health", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        status = "ok" if str(payload.get("status") or "").lower() == "ok" else "error"
        return {"status": status, "backend": "omnivoice", "upstream": payload}

    def synthesize_from_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("text 不能为空")
        output_path = Path(str(payload.get("output_path") or "")).expanduser()
        if not str(output_path):
            raise ValueError("output_path 不能为空")
        backend_options = dict(payload.get("backend_options") or {})
        model = str(backend_options.get("model") or self.model)
        voice = str(backend_options.get("voice") or payload.get("voice_role") or self.voice)
        speed = float(backend_options.get("speed") or 1.0)
        request_payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": "wav",
            "speed": speed,
        }
        language = backend_options.get("language")
        if language:
            request_payload["language"] = str(language)
        instruct = backend_options.get("instruct")
        if instruct:
            request_payload["instruct"] = str(instruct)

        audio = self._post_json(
            f"{self.base_url}/v1/audio/speech",
            request_payload,
            timeout_s=self.timeout_s,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio)
        return {
            "success": True,
            "output_path": str(output_path),
            "backend": "omnivoice",
            "meta": {
                "model": model,
                "voice": voice,
                "note": "ref_wav/ref_text are not used by the OpenAI-compatible OmniVoice endpoint.",
            },
        }


def post_json_bytes(url: str, payload: dict[str, Any], *, timeout_s: int = 300) -> bytes:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return response.read()


def create_handler(adapter: OmniVoiceTtsAdapter) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "LogicCutOmniVoiceTts/1.0"

        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            if self.path != "/health":
                self._send_json({"success": False, "error": "not found"}, status=404)
                return
            try:
                self._send_json(adapter.health())
            except Exception as exc:
                self._send_json({"status": "error", "success": False, "error": str(exc)}, status=503)

        def do_POST(self) -> None:
            if self.path != "/tts":
                self._send_json({"success": False, "error": "not found"}, status=404)
                return
            try:
                payload = self._read_json()
                self._send_json(adapter.synthesize_from_payload(payload))
            except (ValueError, FileNotFoundError) as exc:
                self._send_json({"success": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._send_json({"success": False, "error": str(exc)}, status=502)

        def _read_json(self) -> dict[str, Any]:
            raw_length = self.headers.get("Content-Length", "0")
            content_length = int(raw_length)
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON body 必须是对象")
            return payload

        def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LogicCut OmniVoice /tts compatibility adapter")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8391)
    parser.add_argument("--omnivoice-url", default="http://127.0.0.1:3900")
    parser.add_argument("--model", default="omnivoice")
    parser.add_argument("--voice", default="default")
    parser.add_argument("--timeout-s", type=int, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    adapter = OmniVoiceTtsAdapter(
        base_url=args.omnivoice_url,
        model=args.model,
        voice=args.voice,
        timeout_s=args.timeout_s,
    )
    server = ThreadingHTTPServer((args.host, args.port), create_handler(adapter))
    print(f"LogicCut OmniVoice TTS adapter: http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
