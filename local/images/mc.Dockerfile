# syntax=docker/dockerfile:1.7
# Local development only. Upstream source/license retained; no unpinned download.
FROM library/golang:1.24.6-bookworm@sha256:ab1d1823abb55a9504d2e3e003b75b36dbeb1cbcc4c92593d85a84ee46becc6c AS build
ENV GOTOOLCHAIN=local CGO_ENABLED=0
WORKDIR /src
ADD --checksum=sha256:526ec538e7f83e4bfa631788129b08ec85898ca572ce0523ebf9a597946bea27 https://codeload.github.com/minio/mc/tar.gz/refs/tags/RELEASE.2025-04-16T18-13-26Z /tmp/source.tar.gz
RUN tar -xzf /tmp/source.tar.gz -C /src --strip-components=1 && rm /tmp/source.tar.gz
RUN go build -mod=readonly -trimpath -buildvcs=false -o /out/mc .

FROM library/debian:bookworm-slim@sha256:7ff6ba31527b9e336162fa061746c366c4b2032f4d2cff2078bea43f78efe3f8
COPY --from=build /out/mc /usr/local/bin/mc
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=build /src/LICENSE /usr/share/licenses/mc/LICENSE
ENTRYPOINT ["/usr/local/bin/mc"]
