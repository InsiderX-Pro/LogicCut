"""Runtime compatibility patches for third-party adapters.

Python imports ``sitecustomize`` automatically when this directory is present on
PYTHONPATH. Keep patches tiny and defensive; this file must not import heavy ML
libraries at startup.
"""

from __future__ import annotations

import functools
import inspect


def _patch_huggingface_hub_use_auth_token() -> None:
    try:
        import huggingface_hub
    except Exception:
        return

    fn = getattr(huggingface_hub, "hf_hub_download", None)
    if fn is None:
        return

    try:
        parameters = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return

    if "use_auth_token" in parameters or "token" not in parameters:
        return

    @functools.wraps(fn)
    def hf_hub_download_compat(*args, **kwargs):
        if "use_auth_token" in kwargs and "token" not in kwargs:
            kwargs["token"] = kwargs.pop("use_auth_token")
        else:
            kwargs.pop("use_auth_token", None)
        return fn(*args, **kwargs)

    huggingface_hub.hf_hub_download = hf_hub_download_compat


_patch_huggingface_hub_use_auth_token()
