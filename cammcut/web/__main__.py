"""Run the cammcut web app:  python -m cammcut.web

Serves TLS on the port by default (see tls.py for why): browsers that
auto-upgrade http:// to https:// land on a working listener. Set
CAMMCUT_TLS=off to serve plain HTTP.
"""

import os

import uvicorn

from . import settings, tls


def main() -> None:
    ssl_cert = ssl_key = None
    if os.environ.get("CAMMCUT_TLS", "on").lower() != "off":
        ssl_cert, ssl_key = tls.ensure_cert()
        if ssl_cert is None:
            print("tls: could not create a certificate (openssl missing?) "
                  "— serving plain HTTP")
    uvicorn.run(
        "cammcut.web.app:create_app", factory=True,
        host=settings.HOST, port=settings.PORT,
        ssl_certfile=str(ssl_cert) if ssl_cert else None,
        ssl_keyfile=str(ssl_key) if ssl_key else None,
    )


if __name__ == "__main__":
    main()