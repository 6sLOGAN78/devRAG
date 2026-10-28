"""Approved package-local Chinese dictionaries, loaded without mutable cache or downloads."""

from functools import lru_cache
import warnings


@lru_cache(maxsize=1)
def converter():
    from opencc import OpenCC

    value = OpenCC("t2s")
    value.convert("初始化")
    return value


@lru_cache(maxsize=1)
def segmenter():
    # The pinned legacy package has non-raw regex literals; Python 3.13 warns at compile time.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="invalid escape sequence.*", category=SyntaxWarning)
        import jieba
    value = jieba.Tokenizer()
    # Read only the installed default dictionary. Avoid marshal caches in shared /tmp.
    value.FREQ, value.total = value.gen_pfdict(value.get_dict_file())
    value.initialized = True
    return value


def simplify(text: str) -> str:
    return converter().convert(text)


def words(text: str):
    return segmenter().tokenize(text, mode="search", HMM=False)
