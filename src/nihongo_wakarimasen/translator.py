from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .papago_credentials import load_papago_credentials


class Translator(ABC):
    @abstractmethod
    def translate(self, japanese: str, context: list[str] | None = None) -> str:
        raise NotImplementedError


class TranslatorUnavailable(RuntimeError):
    pass


class CachedTranslator(Translator):
    def __init__(
        self,
        translator: Translator | None = None,
        dictionary_path: Path | None = None,
        user_dictionary_path: Path | None = None,
        translator_factory: Callable[[], Translator] | None = None,
    ) -> None:
        self.translator = translator
        self.translator_factory = translator_factory
        self.dictionary, self.terms = self._load_dictionaries(
            dictionary_path,
            user_dictionary_path,
        )
        self.cache: dict[str, str] = {}

    def translate(self, japanese: str, context: list[str] | None = None) -> str:
        key = self._normalize(japanese)
        if key in self.dictionary:
            return self.dictionary[key]
        dictionary_translation = self._translate_from_dictionary(japanese)
        if dictionary_translation:
            return dictionary_translation
        if key in self.cache:
            return self.cache[key]
        if self.translator is None:
            if self.translator_factory is None:
                raise RuntimeError("No remote translator is configured.")
            self.translator = self.translator_factory()
        korean = self.translator.translate(japanese, context)
        korean = self._apply_term_dictionary(japanese, korean)
        self.cache[key] = korean
        return korean

    def _normalize(self, text: str) -> str:
        compact = " ".join(text.split())
        return compact.strip("\u3002\uff01\uff1f.!?\u3001, ")

    def _split_sentences(self, text: str) -> list[str]:
        split = re.sub(r"([.!?\u3002\uff01\uff1f])\s*", r"\1\n", text).splitlines()
        return [line.strip() for line in split if line.strip()]

    def _translate_from_dictionary(self, japanese: str) -> str | None:
        lines = self._split_sentences(japanese)
        if len(lines) <= 1:
            return None
        translations = []
        for line in lines:
            key = self._normalize(line)
            if key not in self.dictionary:
                return None
            translations.append(self.dictionary[key])
        return "\n".join(translations)

    def _apply_term_dictionary(self, japanese: str, korean: str) -> str:
        japanese_compact = self._normalize(japanese)
        fixed = korean
        for term in self.terms:
            source = term["source"]
            if source not in japanese and self._normalize(source) not in japanese_compact:
                continue
            target = term["target"]
            for bad_output in term["bad_outputs"]:
                if bad_output:
                    fixed = self._replace_bad_output(fixed, bad_output, target)
        return fixed

    def _replace_bad_output(self, korean: str, bad_output: str, target: str) -> str:
        particle_pattern = r"(?:은|는|이|가|을|를|만|도|과|와|로|으로)?"
        return re.sub(re.escape(bad_output) + particle_pattern, target, korean)

    def _load_dictionary(self, dictionary_path: Path | None) -> tuple[dict[str, str], list[dict[str, object]]]:
        if dictionary_path is None or not dictionary_path.exists():
            return {}, []
        data = json.loads(dictionary_path.read_text(encoding="utf-8"))
        exact = data.get("exact", {})
        exact_dictionary = {
            self._normalize(japanese): korean
            for japanese, korean in exact.items()
            if japanese and korean
        }
        terms = []
        for item in data.get("terms", []):
            source = str(item.get("source", "")).strip()
            target = str(item.get("target", "")).strip()
            bad_outputs = item.get("bad_outputs", [])
            if not source or not target or not isinstance(bad_outputs, list):
                continue
            terms.append(
                {
                    "source": source,
                    "target": target,
                    "bad_outputs": [str(value) for value in bad_outputs if str(value)],
                }
            )
        terms.sort(key=lambda term: len(str(term["source"])), reverse=True)
        return exact_dictionary, terms

    def _load_dictionaries(
        self,
        dictionary_path: Path | None,
        user_dictionary_path: Path | None,
    ) -> tuple[dict[str, str], list[dict[str, object]]]:
        dictionary: dict[str, str] = {}
        terms: list[dict[str, object]] = []
        for path in (dictionary_path, user_dictionary_path):
            loaded_dictionary, loaded_terms = self._load_dictionary(path)
            dictionary.update(loaded_dictionary)
            terms.extend(loaded_terms)
        terms.sort(key=lambda term: len(str(term["source"])), reverse=True)
        return dictionary, terms


class JapaneseToKoreanTranslator(Translator):
    def __init__(
        self,
        model: str,
        hints_path: Path | None = None,
        mode: str = "conservative",
        use_hints: bool = True,
    ) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY environment variable is required.")
        from openai import OpenAI

        self.client = OpenAI()
        self.model = model
        self.mode = mode
        self.hints = self._load_hints(hints_path) if use_hints else []

    def translate(self, japanese: str, context: list[str] | None = None) -> str:
        context_text = "\n".join(f"- {item}" for item in context or [])
        hints_text = "\n".join(self.hints) if self.hints else "(none)"
        current_text = "\n".join(self._split_sentences(japanese))
        user_content = (
            "Recent context:\n"
            f"{context_text or '(none)'}\n\n"
            "ASR correction hints:\n"
            f"{hints_text}\n\n"
            "Current ASR text, one sentence per line:\n"
            f"{current_text}"
        )
        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": self._system_prompt(),
                },
                {"role": "user", "content": user_content},
            ],
        )
        return response.output_text.strip()

    def _system_prompt(self) -> str:
        shared = (
            "You translate Japanese ASR text into natural Korean for a listener. "
            "The input comes from speech recognition and may contain errors. "
            "Use ASR correction hints only when they clearly fit the current context. "
            "Do not explain corrections. Return only Korean. "
            "Keep the output short and close to the source. "
            "If the current ASR text has multiple lines, return the same number of Korean lines "
            "in the same order."
        )
        if self.mode == "balanced":
            return (
                shared
                + " Use recent context to infer intended meaning, but do not add events, "
                + "objects, or speaker intent that are not supported by the current ASR text. "
                + "If the ASR text is too noisy or fragmentary to translate, return exactly '불확실'."
            )
        return (
            shared
            + " Be conservative. Translate only what is actually supported by the current ASR text. "
            + "Recent context may disambiguate a word, but must not add new facts, actions, objects, "
            + "or speaker intent that are not present in the current ASR text. "
            + "If the ASR text is fragmentary, noisy, or uncertain, return exactly '불확실'. "
            + "Do not turn unclear fragments into a complete story."
        )

    def _split_sentences(self, text: str) -> list[str]:
        split = re.sub(r"([.!?\u3002\uff01\uff1f])\s*", r"\1\n", text).splitlines()
        lines = [line.strip() for line in split if line.strip()]
        return lines or [text.strip()]

    def _load_hints(self, hints_path: Path | None) -> list[str]:
        if hints_path is None or not hints_path.exists():
            return []

        data = json.loads(hints_path.read_text(encoding="utf-8"))
        hints = []
        for item in data.get("hints", []):
            asr = item.get("asr", "")
            intended = item.get("intended", "")
            korean = item.get("korean", "")
            note = item.get("note", "")
            if asr and intended and korean:
                hints.append(f"- {asr} -> {intended} -> {korean}. {note}".strip())
        return hints


class PapagoJapaneseToKoreanTranslator(Translator):
    endpoint = "https://papago.apigw.ntruss.com/nmt/v1/translation"

    def __init__(
        self,
        timeout_seconds: float = 4.0,
        credentials_path: Path | None = None,
    ) -> None:
        credentials = load_papago_credentials(credentials_path)
        self.client_id = (
            os.getenv("NAVER_CLIENT_ID")
            or os.getenv("PAPAGO_CLIENT_ID")
            or credentials.client_id
        )
        self.client_secret = (
            os.getenv("NAVER_CLIENT_SECRET")
            or os.getenv("PAPAGO_CLIENT_SECRET")
            or credentials.client_secret
        )
        self.endpoint = os.getenv("PAPAGO_API_ENDPOINT", self.endpoint)
        self.timeout_seconds = timeout_seconds
        if not self.client_id or not self.client_secret:
            raise TranslatorUnavailable(
                "Papago translator requires NAVER_CLIENT_ID/NAVER_CLIENT_SECRET "
                "or PAPAGO_CLIENT_ID/PAPAGO_CLIENT_SECRET."
            )

    def translate(self, japanese: str, context: list[str] | None = None) -> str:
        del context
        body = urlencode(
            {
                "source": "ja",
                "target": "ko",
                "text": japanese,
            }
        ).encode("utf-8")
        request = Request(
            self.endpoint,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-NCP-APIGW-API-KEY-ID": self.client_id,
                "X-NCP-APIGW-API-KEY": self.client_secret,
                "X-Naver-Client-Id": self.client_id,
                "X-Naver-Client-Secret": self.client_secret,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Papago translation failed: HTTP {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Papago translation failed: {exc.reason}") from exc
        return data["message"]["result"]["translatedText"].strip()


def create_translator(
    provider: str,
    openai_model: str,
    hints_path: Path | None = None,
    mode: str = "conservative",
    use_hints: bool = True,
    dictionary_path: Path | None = None,
    user_dictionary_path: Path | None = None,
    papago_credentials_path: Path | None = None,
    papago_timeout_seconds: float = 4.0,
) -> Translator:
    if provider == "papago":
        return CachedTranslator(
            dictionary_path=dictionary_path,
            user_dictionary_path=user_dictionary_path,
            translator_factory=lambda: PapagoJapaneseToKoreanTranslator(
                papago_timeout_seconds,
                papago_credentials_path,
            ),
        )
    if provider == "openai":
        return CachedTranslator(
            dictionary_path=dictionary_path,
            user_dictionary_path=user_dictionary_path,
            translator_factory=lambda: JapaneseToKoreanTranslator(
                openai_model,
                hints_path,
                mode,
                use_hints,
            ),
        )
    raise ValueError(f"Unsupported translator provider: {provider}")
