def get_text(lang: str, key: str, **kwargs) -> str:
    from app.locales.uk import TEXTS as uk_texts
    from app.locales.ru import TEXTS as ru_texts

    texts = ru_texts if lang == "ru" else uk_texts
    text = texts.get(key, uk_texts.get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text


def detect_language(language_code: str | None) -> str:
    if not language_code:
        return "uk"
    code = language_code.lower()
    if code.startswith("ru"):
        return "ru"
    # Default to uk for 'uk' and any unsupported language
    return "uk"
