class ValidationError(ValueError):
    pass


def integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValidationError(f"{name} 必须是 {low}–{high} 的整数")
    return value
