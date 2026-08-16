def params_to_str(obj: dict, level: int, max_level: int) -> str:
    if level >= max_level or not isinstance(obj, dict):
        return str(obj)

    return_str = ""
    for key in sorted(obj.keys()):  # Sort the keys in ascending order
        value = obj[key]
        if isinstance(value, dict):
            return_str += params_to_str(value, level + 1, max_level)
        elif isinstance(value, list):
            return_str += f"{key}"
            for sub_value in value:
                return_str += params_to_str(sub_value, level + 1, max_level)
        else:
            value = "null" if value is None else value
            return_str += f"{key}{value}"
    return return_str
