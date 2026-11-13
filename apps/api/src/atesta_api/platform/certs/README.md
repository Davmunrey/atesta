# Pinned Amazon RDS CA bundle

`rds-eu-south-2-bundle.pem` is the CA bundle `platform/db.py` passes as `sslrootcert` whenever
`sslmode` is `verify-full` (tenant-data-layer spec). Neither the URL, `PGSSLROOTCERT` nor
`~/.postgresql/root.crt` can replace it.

| Field | Value |
|---|---|
| Source | https://truststore.pki.rds.amazonaws.com/eu-south-2/eu-south-2-bundle.pem |
| Fetched | 2026-11-13 |
| SHA-256 | `6e4db6870d865a83140270728f62fbdb73202a3a017dc500ae2605e3d17344c0` |
| Contents | Amazon RDS eu-south-2 Root CA RSA2048 G1 (expires 2062), RSA4096 G1 and ECC384 G1 (2122) |

Rotation: download the bundle again from the source URL, check it against the AWS documentation
("Using SSL/TLS to encrypt a connection to a DB instance or cluster"), replace the file and update
the SHA-256 here and in `tests/test_db_tls.py` in the same PR.
