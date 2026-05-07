# certbot-tcc

A Certbot DNS-01 authenticator plugin powered by Tencent Cloud DNSPod API 3.0, enabling fully automated Let's Encrypt certificate issuance — including wildcard certificates.

English | [简体中文](README_CN.md)

---

## How It Works

Before issuing a certificate, Let's Encrypt requires proof of domain ownership. The DNS-01 challenge requires adding a specific TXT record to your domain's DNS. This plugin automates the creation and cleanup of that TXT record via the Tencent Cloud DNSPod API, requiring zero manual intervention.

## Features

- Supports regular domains and wildcard domains (`*.example.com`)
- Automatically creates and removes DNS TXT records — no manual steps required
- Built on Tencent Cloud DNSPod API 3.0 (Signature V3, TC3-HMAC-SHA256)
- Handles multi-level subdomains with longest-suffix matching
- Precise value-based record deletion to avoid removing unrelated TXT records

## Requirements

- Python >= 3.9
- Certbot >= 2.0.0
- A Tencent Cloud account with the target domain hosted on DNSPod

## Installation

```bash
pip install git+https://github.com/LideDing/certbot-tcc.git
```

Or install from source:

```bash
git clone https://github.com/LideDing/certbot-tcc.git
cd certbot-tcc
pip install .
```

## Configuration

### 1. Obtain API Credentials

Go to [Tencent Cloud API Key Management](https://console.cloud.tencent.com/cam/capi) to get your `SecretId` and `SecretKey`.

### 2. Create a Credentials File

Create a credentials file (e.g. `~/tcc.ini`) based on `tcc.ini.example`:

```ini
certbot_tcc_secret_id  = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
certbot_tcc_secret_key = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. Secure the File

```bash
chmod 600 ~/tcc.ini
```

> **Security Note**: This file contains sensitive credentials. Never commit it to version control. Certbot will emit a warning if file permissions are too permissive.

## Usage

### Obtain a Certificate

```bash
certbot certonly \
  --authenticator certbot-tcc \
  --certbot-tcc-credentials ~/tcc.ini \
  -d example.com -d '*.example.com'
```

### Auto-Renewal

Certbot's automatic renewal mechanism will invoke this plugin automatically — no extra configuration needed. To trigger renewal manually:

```bash
certbot renew
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--certbot-tcc-credentials` | Path to the credentials INI file (required) | — |
| `--certbot-tcc-propagation-seconds` | Seconds to wait for DNS propagation | `10` |

Example with extended propagation wait (useful when DNS is slow to propagate):

```bash
certbot certonly \
  --authenticator certbot-tcc \
  --certbot-tcc-credentials ~/tcc.ini \
  --certbot-tcc-propagation-seconds 60 \
  -d example.com -d '*.example.com'
```

## Development

### Install Dev Dependencies

```bash
pip install pytest
pip install -e .
```

### Run Tests

```bash
pytest tests/ -v
```

Tests use `unittest.mock` to simulate the Tencent Cloud SDK — no real API credentials required.

## Dependencies

| Package | Description |
|---------|-------------|
| `certbot >= 2.0.0` | Certbot core library |
| `tencentcloud-sdk-python-dnspod` | Official Tencent Cloud Python SDK (DNSPod module) |
| `zope.interface` | Interface declaration for Certbot plugins |

## License

[MIT](https://opensource.org/licenses/MIT)
