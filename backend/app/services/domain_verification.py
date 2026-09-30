"""Real DNS verification for a restaurant's custom domain.

The admin settings UI's promise is simple: point your domain's DNS at this platform, then ask us to
verify it. So the check here is exactly that — does ``custom_domain`` currently resolve to the same
place ``PLATFORM_DOMAIN`` does? That's a plain A/AAAA/CNAME-terminus equality check via the stdlib's own
resolver (``socket.getaddrinfo``), no DNS library dependency needed.

This is not a domain-*ownership* proof (a TXT-record challenge-response would be that) — it's a
points-here proof, which is the right bar for "will this address our platform", and is what the UI
already advertises. Add a TXT-token flow later only if ownership (not just current DNS pointing) needs
to be proven independently of hosting.
"""

import logging
import socket

logger = logging.getLogger(__name__)


def verify_dns(custom_domain: str, platform_domain: str) -> bool:
    """True if ``custom_domain`` resolves to at least one of the same addresses as ``platform_domain``."""
    if not platform_domain:
        # No real platform domain configured (e.g. local dev's PLATFORM_DOMAIN=localhost) — nothing to
        # compare against, so nothing can ever verify. Callers should treat this as a setup gap, not
        # silently pass every domain.
        return False
    try:
        domain_ips = {info[4][0] for info in socket.getaddrinfo(custom_domain, None)}
        platform_ips = {info[4][0] for info in socket.getaddrinfo(platform_domain, None)}
    except socket.gaierror:
        return False
    return bool(domain_ips & platform_ips)
