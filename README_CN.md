# certbot-tcc

基于腾讯云 DNSPod API 3.0 的 Certbot DNS-01 认证插件，支持自动申请 Let's Encrypt 证书（含通配符证书）。

[English](README.md) | 简体中文

---

## 原理

Let's Encrypt 颁发证书前，需要验证你对域名的控制权。DNS-01 验证方式要求在域名 DNS 中添加一条特定的 TXT 记录。本插件通过腾讯云 DNSPod API 自动完成该 TXT 记录的创建与清理，实现无需人工干预的自动化证书申请。

## 特性

- 支持普通域名及通配符域名（`*.example.com`）
- 自动创建 / 清理 DNS TXT 记录，全程无需手动操作
- 基于腾讯云 DNSPod API 3.0（签名 V3，TC3-HMAC-SHA256）
- 支持多级子域名，自动匹配最长后缀的主域名
- 删除记录时精确匹配值，不误删其他同名 TXT 记录

## 环境要求

- Python >= 3.9
- Certbot >= 2.0.0
- 腾讯云账号，且目标域名已托管在 DNSPod

## 安装

```bash
pip install git+https://github.com/LideDing/certbot-tcc.git
```

或从源码安装：

```bash
git clone https://github.com/LideDing/certbot-tcc.git
cd certbot-tcc
pip install .
```

## 配置

### 1. 获取 API 密钥

前往 [腾讯云 API 密钥管理](https://console.cloud.tencent.com/cam/capi) 获取 `SecretId` 和 `SecretKey`。

### 2. 创建凭证文件

参考 `tcc.ini.example` 创建凭证文件（如 `~/tcc.ini`）：

```ini
certbot_tcc_secret_id  = AKIDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
certbot_tcc_secret_key = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. 设置文件权限

```bash
chmod 600 ~/tcc.ini
```

> **安全提示**：凭证文件包含敏感信息，请勿提交到版本控制系统。文件权限过宽时 certbot 会输出安全警告。

## 使用

### 申请证书

```bash
certbot certonly \
  --authenticator certbot-tcc \
  --certbot-tcc-credentials ~/tcc.ini \
  -d example.com -d '*.example.com'
```

### 自动续期

certbot 自动续期时会自动调用本插件，无需额外配置。可用以下命令手动触发续期：

```bash
certbot renew
```

### 常用参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--certbot-tcc-credentials` | 凭证 INI 文件路径（必填） | — |
| `--certbot-tcc-propagation-seconds` | 等待 DNS 记录生效的秒数 | `10` |

延长等待时间示例（适用于 DNS 生效较慢的情况）：

```bash
certbot certonly \
  --authenticator certbot-tcc \
  --certbot-tcc-credentials ~/tcc.ini \
  --certbot-tcc-propagation-seconds 60 \
  -d example.com -d '*.example.com'
```

## 开发

### 安装开发依赖

```bash
pip install pytest
pip install -e .
```

### 运行测试

```bash
pytest tests/ -v
```

测试使用 `unittest.mock` 模拟腾讯云 SDK，无需真实 API 密钥即可运行。

## 依赖

| 包 | 说明 |
|----|------|
| `certbot >= 2.0.0` | Certbot 核心库 |
| `tencentcloud-sdk-python-dnspod` | 腾讯云官方 Python SDK（DNSPod 模块） |
| `zope.interface` | Certbot 插件接口声明 |

## 许可证

[MIT](https://opensource.org/licenses/MIT)
