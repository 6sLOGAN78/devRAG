"""Bounded capability codecs shared by structure flags and legacy credential rows."""

TYPE_BITS = {"chat": 1, "embedding": 2, "vision": 8, "rerank": 16}


def types_for_bits(flags):
    return tuple(name for name, bit in TYPE_BITS.items() if type(flags) is int and flags & bit)


def legacy_types(value):
    if not isinstance(value, str):
        return ()
    return tuple(kind for kind in value.split(",") if kind in TYPE_BITS)


def legacy_union(value, kind):
    requested = set(legacy_types(value)) | {kind}
    return ",".join(name for name in TYPE_BITS if name in requested)
