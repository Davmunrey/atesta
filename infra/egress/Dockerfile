# Scan egress proxy (scanner-connectors spec, AWS runner; issue 454): Envoy (Apache-2.0, rule 4),
# its distroless image pinned by digest, plus the allowlist in envoy.yaml. The base image's
# entrypoint is /usr/local/bin/envoy; the deploy workflow builds and pushes this image.
FROM envoyproxy/envoy:distroless-v1.40.2@sha256:09ca6f2140a61ad8df11779a4a30d52b48433d444466328494f9188c9c35eded
COPY --chown=0:0 --chmod=644 infra/egress/envoy.yaml /etc/envoy/envoy.yaml
USER 10001
EXPOSE 3128
CMD ["-c", "/etc/envoy/envoy.yaml", "--log-level", "warn", "--disable-hot-restart"]
