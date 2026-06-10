# Third Party Notices

## Comment Crawling References

LogicCut's V0.2.2 comment crawler invokes `yt-dlp` for YouTube comments and uses Bilibili public web API endpoints directly for Bilibili comments. The implementation references public repository documentation and API examples, but does not vendor source code from the Bilibili reference projects.

- YouTube comments engine: https://github.com/yt-dlp/yt-dlp
- Bilibili API reference: https://github.com/Nemo2011/bilibili-api
- Bilibili API collection reference: https://github.com/SocialSisterYi/bilibili-API-collect
- Real page screenshot engine: https://github.com/microsoft/playwright
- Comment freeze-frame image composition: https://github.com/python-pillow/Pillow

## Translation / ASR / TTS References

LogicCut's built-in local translation pipeline does not vendor model weights. It can use user-installed ASR and optional TTS backends from the following upstream projects:

- faster-whisper: https://github.com/SYSTRAN/faster-whisper
- faster-whisper models: https://huggingface.co/Systran/faster-whisper-base and https://huggingface.co/Systran/faster-whisper-large-v3
- pyannote diarization: https://huggingface.co/pyannote/speaker-diarization-3.1
- RGAD Cross-Lingual TTS: https://github.com/piedpiperG/rgad-crosslingual-tts and https://huggingface.co/isabeth/rgad-crosslingual-tts
- Fish Speech: https://github.com/fishaudio/fish-speech
- IndexTTS2: https://github.com/index-tts/index-tts and https://huggingface.co/IndexTeam/IndexTTS-2
- OmniVoice: https://github.com/k2-fsa/OmniVoice and https://huggingface.co/k2-fsa/OmniVoice
- OmniVoice Studio: https://github.com/debpalash/OmniVoice-Studio

Users are responsible for each upstream project's license, model card, gated access, and acceptable-use requirements.

## subcap 0.2.2

LogicCut's `subcap-ass` subtitle renderer adapts the ASS style model, SRT bypass flow, and FFmpeg/libass burn-in strategy from `subcap` 0.2.2.

- Project: https://pypi.org/project/subcap/
- License: MIT
- Copyright: Copyright (c) 2026 Joseph Nordqvist

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
