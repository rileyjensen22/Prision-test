Optional: a certificate authority file for image builds behind a proxy that inspects TLS.

`make demo` copies the file named in `ISD_EXTRA_CA` here as `extra-ca.pem` (git ignores it) and the
Dockerfiles use it for `pip` and `npm` while building. With no file here, nothing changes.
