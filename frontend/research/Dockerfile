FROM node:22-bookworm-slim
USER root
# Use the public CA bundle shipped with Node, and HTTPS for package retrieval.
RUN node -e "const f=require('fs');f.mkdirSync('/etc/ssl/certs',{recursive:true});f.writeFileSync('/etc/ssl/certs/ca-certificates.crt',require('tls').rootCertificates.join('\n'));const p='/etc/apt/sources.list.d/debian.sources';f.writeFileSync(p,f.readFileSync(p,'utf8').replaceAll('http://','https://'))"
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tor libimage-exiftool-perl wireshark-common yara && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/research
COPY research/package.json research/package-lock.json ./
RUN npm ci --omit=dev
COPY skills ./skills
COPY research/smoke.mjs ./research/smoke.mjs
COPY research/torrc /etc/tor/torrc
USER node
CMD ["tor", "-f", "/etc/tor/torrc"]
