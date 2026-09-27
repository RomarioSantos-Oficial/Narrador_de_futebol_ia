"""Coach details supplied by match providers."""
from urllib.parse import urlsplit


def normalize_coach(value, source):
    if not isinstance(value, dict):
        return None
    name = value.get('popularName') or value.get('name')
    if not isinstance(name, str) or not name.strip():
        return None
    photo = value.get('photo') or ''
    try:
        url = urlsplit(photo)
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            photo = ''
    except (ValueError, TypeError, AttributeError):
        photo = ''
    return {'name': name.strip(), 'source': source, **({'photo': photo} if photo else {})}
