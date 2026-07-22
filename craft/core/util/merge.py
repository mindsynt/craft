def merge_deep(*dicts: dict) -> dict:
    """深度合并字典"""
    result = {}
    for d in dicts:
        for k, v in d.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = merge_deep(result[k], v)
            else:
                result[k] = v
    return result
