"""Korean to English translation."""

from __future__ import annotations

_translator = None


def translate_ko_en(text: str) -> str:
    if not text.strip():
        return text
    global _translator
    try:
        if _translator is None:
            from transformers import MarianMTModel, MarianTokenizer

            model_name = "Helsinki-NLP/opus-mt-ko-en"
            _translator = (
                MarianTokenizer.from_pretrained(model_name),
                MarianMTModel.from_pretrained(model_name),
            )
        tokenizer, model = _translator
        batch = tokenizer.prepare_seq2seq_batch([text], return_tensors="pt")
        outputs = model.generate(**batch)
        return tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]
    except Exception:
        return text
