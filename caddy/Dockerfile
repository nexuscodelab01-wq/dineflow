# The stock Caddy image can't do DNS-01 ACME challenges, which a wildcard certificate (*.dineflow.io —
# every restaurant's subdomain) requires: Let's Encrypt won't issue a wildcard cert through the normal
# "prove you control port 80/443" method, only by proving control over the domain's DNS. This builds a
# Caddy binary with the Cloudflare DNS plugin so it can create the short-lived TXT record itself.
FROM caddy:2-builder AS builder

RUN xcaddy build --with github.com/caddy-dns/cloudflare

FROM caddy:2

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
